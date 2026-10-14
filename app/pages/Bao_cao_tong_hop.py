import streamlit as st
from pathlib import Path
import sys
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import get_all_invoices, get_confirmed_invoices, get_recent_jobs
from src.structuring.invoice_validation import validate_invoice_data
from src.structuring.duplicate_detection import find_duplicate_groups
from app.components.sidebar_nav import render_sidebar

st.set_page_config(page_title="Báo cáo tổng hợp", layout="wide")
render_sidebar("report")
css_path = Path(__file__).resolve().parents[1] / "style.css"
st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# --- Header ---
col_title, col_status, col_period = st.columns([3, 1, 1])
with col_title:
    st.title("Báo cáo tổng hợp")
    st.caption("Tổng quan hóa đơn & kế toán")
with col_status:
    st.markdown('<div class="status-badge status-done">🟢 Hệ thống hoạt động</div>', unsafe_allow_html=True)
with col_period:
    now = datetime.now()
    st.markdown(f'<div class="status-badge" style="background:#EEF2FF;color:#4F46E5;">Kỳ: T{now.month}/{now.year}</div>', unsafe_allow_html=True)

st.subheader("Báo cáo sai lệch dữ liệu")
all_invoices = get_all_invoices()
invoices_with_findings = []
for invoice in all_invoices:
    findings = validate_invoice_data(invoice)
    if findings:
        invoices_with_findings.append({
            "ID": invoice.get("id"),
            "Nhà cung cấp": invoice.get("ten_cong_ty_ban") or "Chưa xác định",
            "Ngày lập": invoice.get("ngay_lap") or "Chưa có",
            "Trạng thái": invoice.get("accounting_status") or "Chưa xác định",
            "Số cảnh báo": len(findings),
            "Chi tiết cần rà soát": " | ".join(findings),
        })

warning_count = sum(row["Số cảnh báo"] for row in invoices_with_findings)
metric_invoice, metric_findings = st.columns(2)
metric_invoice.metric("Hóa đơn cần rà soát", len(invoices_with_findings))
metric_findings.metric("Tổng số cảnh báo", warning_count)
if invoices_with_findings:
    st.dataframe(invoices_with_findings, use_container_width=True, hide_index=True)
else:
    st.success("Không phát hiện sai lệch theo các quy tắc kiểm tra hiện có.")

st.caption(
    "Các cảnh báo chỉ hỗ trợ rà soát, không tự sửa dữ liệu và không thay thế việc kiểm tra hóa đơn gốc."
)
st.divider()

st.subheader("Hóa đơn có khả năng bị nhập trùng")
duplicate_groups = find_duplicate_groups(all_invoices)
if duplicate_groups:
    duplicate_rows = []
    for group in duplicate_groups:
        duplicate_rows.append({
            "Mã số thuế bên bán": group["seller_tax_id"],
            "Số hóa đơn": group["invoice_number"],
            "Các bản ghi": ", ".join(
                f"#{invoice.get('id')}" for invoice in group["invoices"]
            ),
            "Ngày lập khớp": "Có" if group["dates_match"] else "Không / thiếu dữ liệu",
            "Tổng thanh toán khớp": "Có" if group["amounts_match"] else "Không / thiếu dữ liệu",
            "Đánh giá": "Trùng khớp" if group["exact_match"] else "Nghi trùng - cần rà soát",
        })
    duplicate_invoice_ids = {
        invoice.get("id")
        for group in duplicate_groups
        for invoice in group["invoices"]
    }
    duplicate_col1, duplicate_col2 = st.columns(2)
    duplicate_col1.metric("Nhóm nghi trùng", len(duplicate_groups))
    duplicate_col2.metric("Hóa đơn cần rà soát", len(duplicate_invoice_ids))
    st.dataframe(duplicate_rows, use_container_width=True, hide_index=True)
else:
    st.success("Chưa phát hiện nhóm hóa đơn trùng theo mã số thuế bên bán và số hóa đơn.")
st.caption(
    "Hệ thống đối chiếu mã số thuế bên bán và số hóa đơn để tìm ứng viên, "
    "sau đó so ngày lập và tổng thanh toán. Kết quả chỉ là cảnh báo; không tự xóa hay chặn xử lý."
)
st.divider()

invoices = get_confirmed_invoices()

if not invoices:
    st.info("Chưa có dữ liệu để báo cáo.")
    st.stop()

df = pd.DataFrame(invoices)
df["created_at"] = pd.to_datetime(df["created_at"])
invoice_dates = pd.to_datetime(df["ngay_lap"], dayfirst=True, errors="coerce")
df["thang"] = invoice_dates.fillna(df["created_at"]).dt.to_period("M")

monthly = df.groupby("thang").agg(
    so_luong=("id", "count"),
    gia_tri=("tong_thanh_toan", "sum"),
    tien_hang=("tong_tien_hang", "sum"),
).reset_index()
monthly["thue"] = monthly["gia_tri"] - monthly["tien_hang"]
monthly["tb_hoa_don"] = monthly["gia_tri"] / monthly["so_luong"]
monthly = monthly.sort_values("thang").tail(6).reset_index(drop=True)
monthly["thang_label"] = monthly["thang"].astype(str)


def pct_change(series: pd.Series) -> float:
    """% thay đổi giữa 2 kỳ gần nhất, an toàn khi chưa đủ dữ liệu hoặc mẫu số = 0."""
    if len(series) < 2 or series.iloc[-2] == 0:
        return 0.0
    return ((series.iloc[-1] - series.iloc[-2]) / series.iloc[-2]) * 100


def sparkline(series: pd.Series, color: str):
    fig = go.Figure(go.Scatter(
        y=series, mode="lines", line=dict(color=color, width=2.2),
        fill="tozeroy", fillcolor=color + "22",
    ))
    fig.update_layout(
        height=46, margin=dict(l=0, r=0, t=2, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    return fig


def metric_card(col, icon, icon_bg, label, value_str, trend_pct, series, spark_color):
    with col:
        with st.container(border=True):
            st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px;">
                    <div style="width:38px; height:38px; border-radius:10px; background:{icon_bg};
                                display:flex; align-items:center; justify-content:center; font-size:17px;">
                        {icon}
                    </div>
                    <div style="color:#64748B; font-size:13px; font-weight:600;">{label}</div>
                </div>
                <div style="font-weight:800; font-size:26px; color:#0F172A; margin-top:10px;">{value_str}</div>
            """, unsafe_allow_html=True)

            trend_color = "#16A34A" if trend_pct >= 0 else "#DC2626"
            arrow = "↑" if trend_pct >= 0 else "↓"
            st.markdown(
                f'<div style="font-size:12px; color:{trend_color}; font-weight:600; margin-top:2px;">'
                f'{arrow} {abs(trend_pct):.1f}% so kỳ trước</div>',
                unsafe_allow_html=True,
            )

            st.plotly_chart(sparkline(series, spark_color), use_container_width=True,
                             config={"displayModeBar": False}, key=f"spark_{label}")


# ===== 4 thẻ số liệu có xu hướng + sparkline =====
c1, c2, c3, c4 = st.columns(4)

metric_card(c1, "#", "#EEF2FF", "Hóa đơn đã hạch toán", f"{len(df)}",
            pct_change(monthly["so_luong"]), monthly["so_luong"], "#4F46E5")

metric_card(c2, "đ", "#ECFDF5", "Tổng giá trị",
            f"{df['tong_thanh_toan'].sum()/1_000_000:,.1f}M đ",
            pct_change(monthly["gia_tri"]), monthly["gia_tri"], "#16A34A")

metric_card(c3, "%", "#F5F3FF", "Thuế GTGT",
            f"{(df['tong_thanh_toan'].sum() - df['tong_tien_hang'].sum())/1_000_000:,.1f}M đ",
            pct_change(monthly["thue"]), monthly["thue"], "#7C3AED")

metric_card(c4, "Ø", "#FFFBEB", "Giá trị TB/hóa đơn",
            f"{(df['tong_thanh_toan'].sum()/len(df)):,.0f} đ",
            pct_change(monthly["tb_hoa_don"]), monthly["tb_hoa_don"], "#D97706")

st.write("")

# ===== Card biểu đồ giá trị theo tháng + donut thuế =====
col_chart, col_donut = st.columns([1.6, 1])

with col_chart:
    with st.container(border=True):
        peak = monthly["gia_tri"].max()
        avg = monthly["gia_tri"].mean()

        head_l, head_r = st.columns([2, 1.3])
        with head_l:
            st.markdown("**Giá trị hóa đơn**")
            st.caption(f"{len(monthly)} tháng gần nhất · triệu đ")
        with head_r:
            st.markdown(
                f'<div style="text-align:right; font-size:12px; color:#64748B; padding-top:4px;">'
                f'Đỉnh: <b style="color:#0F172A;">{peak/1_000_000:,.0f}M đ</b> &nbsp; '
                f'TB: <b style="color:#0F172A;">{avg/1_000_000:,.0f}M đ</b></div>',
                unsafe_allow_html=True,
            )

        gia_tri_m = (monthly["gia_tri"] / 1_000_000).round(1)
        colors = ["#C7D2FE"] * (len(monthly) - 1) + ["#4F46E5"]

        # Đổi nhãn tháng sang định dạng tiếng Việt dễ đọc, ví dụ "T12/2025"
        month_labels_vn = monthly["thang"].apply(lambda p: f"T{p.month}/{p.year}")

        fig1 = go.Figure(go.Bar(
            x=month_labels_vn, y=gia_tri_m,
            marker_color=colors, marker_cornerradius=6,
            text=gia_tri_m, textposition="outside",
        ))
        fig1.update_layout(
            height=270, margin=dict(l=10, r=10, t=20, b=10),
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(showgrid=False, visible=False),
            xaxis=dict(type="category"),  # QUAN TRỌNG: ép trục X là danh mục, không để Plotly tự đoán là ngày tháng
        )
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

with col_donut:
    with st.container(border=True):
        st.markdown("**Phân bổ thuế GTGT**")
        st.caption(f"Kỳ {now.month}/{now.year}")

        goods_value = df["tong_tien_hang"].sum()
        vat_value = df["tong_thanh_toan"].sum() - goods_value

        donut = go.Figure(go.Pie(
            labels=["Tiền hàng", "Thuế GTGT"], values=[goods_value, vat_value],
            hole=0.68, marker=dict(colors=["#4F46E5", "#F59E0B"]),
            textinfo="none", hovertemplate="%{label}: %{value:,.0f} đ<extra></extra>",
        ))
        donut.update_layout(
            height=190, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
            paper_bgcolor="white",
            annotations=[dict(
                text=f"{(goods_value+vat_value)/1_000_000:,.1f}M<br><span style='font-size:11px;color:#94A3B8;'>đ</span>",
                x=0.5, y=0.5, showarrow=False, font=dict(size=17, color="#0F172A"),
            )],
        )
        st.plotly_chart(donut, use_container_width=True, config={"displayModeBar": False})

        legend_rows = [
            ("#4F46E5", "Tiền hàng", goods_value),
            ("#F59E0B", "Thuế GTGT", vat_value),
        ]
        for color, label, val in legend_rows:
            pct = (val / (goods_value + vat_value) * 100) if (goods_value + vat_value) else 0
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                <span style="width:8px; height:8px; border-radius:50%; background:{color};"></span>
                <span style="flex:1; font-size:13px; color:#1E293B;">{label}</span>
                <span style="font-size:13px; font-weight:700; color:#0F172A;">{val:,.0f} đ</span>
            </div>
            <div style="background:#F1F5F9; border-radius:999px; height:5px; margin:4px 0 0 16px;">
                <div style="background:{color}; height:5px; border-radius:999px; width:{pct:.0f}%;"></div>
            </div>
            """, unsafe_allow_html=True)

st.write("")

# ===== Top nhà cung cấp + Hoạt động hôm nay =====
col_sup, col_activity = st.columns(2)

with col_sup:
    with st.container(border=True):
        head_l, head_r = st.columns([3, 1])
        head_l.markdown("**Top nhà cung cấp**")
        head_l.caption(f"T{now.month}/{now.year} · theo giá trị")

        top_suppliers = (
            df.assign(ten_cong_ty_ban=df["ten_cong_ty_ban"].fillna("Chưa xác định"))
            .groupby("ten_cong_ty_ban")
            .agg(so_luong=("id", "count"), tong_tien=("tong_thanh_toan", "sum"))
            .sort_values("tong_tien", ascending=False)
            .head(5)
            .reset_index()
        )

        if top_suppliers.empty:
            st.info("Chưa có dữ liệu nhà cung cấp.")
        else:
            max_value = top_suppliers["tong_tien"].max()
            for i, row in top_suppliers.iterrows():
                pct = (row["tong_tien"] / max_value) * 100
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:12px; padding:9px 0;
                            {'border-top:1px solid #F1F5F9;' if i > 0 else ''}">
                    <div style="width:22px; height:22px; border-radius:6px; background:#EEF2FF; color:#4F46E5;
                                display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;">
                        {i+1:02d}
                    </div>
                    <div style="flex:1;">
                        <div style="font-weight:600; color:#0F172A; font-size:13.5px;">{row['ten_cong_ty_ban']}</div>
                        <div style="background:#F1F5F9; border-radius:999px; height:5px; margin-top:5px; width:160px;">
                            <div style="background:#4F46E5; height:5px; border-radius:999px; width:{pct:.0f}%;"></div>
                        </div>
                        <div style="font-size:11px; color:#94A3B8; margin-top:2px;">{row['so_luong']} hóa đơn</div>
                    </div>
                    <div style="font-weight:700; color:#0F172A; font-size:13.5px;">{row['tong_tien']:,.0f} đ</div>
                </div>
                """, unsafe_allow_html=True)

with col_activity:
    with st.container(border=True):
        st.markdown("**Hoạt động hôm nay**")
        st.caption(now.strftime("%d/%m/%Y"))

        today_jobs = [
            j for j in get_recent_jobs(limit=50)
            if j["created_at"].date() == now.date()
        ]

        STATUS_DOT = {
            "success": "#16A34A",
            "duplicate": "#7C3AED",
            "processing": "#D97706",
            "failed": "#DC2626",
        }
        STATUS_TEXT = {
            "success": "Hoàn tất",
            "duplicate": "Trùng hóa đơn",
            "processing": "Đang xử lý",
            "failed": "Lỗi",
        }

        if not today_jobs:
            st.info("Chưa có hoạt động nào hôm nay.")
        else:
            for i, job in enumerate(today_jobs[:6]):
                dot = STATUS_DOT.get(job["status"], "#94A3B8")
                text = STATUS_TEXT.get(job["status"], job["status"])
                time_str = job["created_at"].strftime("%H:%M")
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px; padding:8px 0;
                            {'border-top:1px solid #F1F5F9;' if i > 0 else ''}">
                    <span style="width:7px; height:7px; border-radius:50%; background:{dot}; flex-shrink:0;"></span>
                    <div style="flex:1; font-size:13px; color:#1E293B;">{job['file_name']}</div>
                    <div style="font-size:11px; color:#94A3B8;">{time_str}</div>
                    <div style="font-size:11px; color:{dot}; font-weight:600; min-width:60px; text-align:right;">{text}</div>
                </div>
                """, unsafe_allow_html=True)