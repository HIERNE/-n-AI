from pathlib import Path

import streamlit as st
st.set_page_config(
    page_title="Báo cáo tổng hợp - InvoiceAI",
    page_icon=str(Path(__file__).resolve().parents[1] / "assets" / "invoiceai_logo.png"),
    layout="wide",
)

import sys
import html
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db_handler import (
    get_all_invoices,
    get_confirmed_invoices,
    get_recent_jobs,
)
from src.structuring.invoice_validation import validate_invoice_data
from src.structuring.duplicate_detection import find_duplicate_groups
from app.components.auth import render_account_menu, require_auth
from app.components.sidebar_nav import render_sidebar

user = require_auth()
USER_ID = int(user["id"])
IS_ADMIN = user["role"] == "admin"
render_sidebar("report")
render_account_menu()

# Nạp style.css chuẩn hệ thống
css_path = Path(__file__).resolve().parents[1] / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# --- Header Banner Kỹ thuật ---
now = datetime.now()
st.markdown(f"""
<div class="page-header">
    <div class="page-header-left">
        <div class="page-header-badge"><span>📈</span> BI &amp; FINANCIAL INTELLIGENCE</div>
        <h1>Báo cáo tổng hợp &amp; Kiểm toán</h1>
        <p>Phân tích chỉ số tài chính, rà soát tính toàn vẹn dữ liệu hóa đơn và đối soát lịch sử hệ thống</p>
    </div>
    <div style="display:flex; align-items:center; gap:12px; z-index:1;">
        <div class="header-period-pill">
            <span>Kỳ báo cáo</span>
            T{now.month:02d}/{now.year}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Tải dữ liệu toàn hệ thống
all_invoices = get_all_invoices(user_id=USER_ID, is_admin=IS_ADMIN)
confirmed_invoices = get_confirmed_invoices(user_id=USER_ID, is_admin=IS_ADMIN)

# Xử lý dữ liệu kiểm toán sai lệch
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
duplicate_groups = find_duplicate_groups(all_invoices)
duplicate_invoice_ids = {
    invoice.get("id")
    for group in duplicate_groups
    for invoice in group["invoices"]
}

# --- TABS ĐIỀU HƯỚNG BÁO CÁO KỸ THUẬT ---
tab_overview, tab_audit, tab_duplicates, tab_activity = st.tabs([
    "📊 Tổng quan Tài chính", 
    f"⚠️ Kiểm toán sai lệch ({len(invoices_with_findings)})", 
    f"🔁 Đối soát trùng lặp ({len(duplicate_groups)})", 
    "⏱️ Nhật ký hoạt động"
])

# ================= TAB 1: TỔNG QUAN TÀI CHÍNH =================
with tab_overview:
    if not confirmed_invoices:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">📊</div>
            <h3>Chưa có dữ liệu hạch toán để báo cáo</h3>
            <p>Vui lòng phê duyệt các hóa đơn ở mục <strong>Trích xuất dữ liệu</strong> để hiển thị biểu đồ phân tích tài chính.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        df = pd.DataFrame(confirmed_invoices)
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

        def pct_change(series: pd.Series) -> float:
            if len(series) < 2 or series.iloc[-2] == 0:
                return 0.0
            return ((series.iloc[-1] - series.iloc[-2]) / series.iloc[-2]) * 100

        def sparkline(series: pd.Series, color: str):
            fig = go.Figure(go.Scatter(
                y=series, mode="lines", line=dict(color=color, width=2.2),
                fill="tozeroy", fillcolor=color + "22",
            ))
            fig.update_layout(
                height=42, margin=dict(l=0, r=0, t=2, b=0),
                xaxis=dict(visible=False), yaxis=dict(visible=False),
                plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
            )
            return fig

        def render_metric_card(col, icon, icon_bg, label, value_str, trend_pct, series, spark_color):
            with col:
                with st.container(border=True):
                    st.markdown(f"""
                        <div style="display:flex; align-items:center; gap:10px;">
                            <div style="width:36px; height:36px; border-radius:10px; background:{icon_bg};
                                        display:flex; align-items:center; justify-content:center; font-size:16px;">
                                {icon}
                            </div>
                            <div style="color:#64748B; font-size:12px; font-weight:700; text-transform:uppercase;">{label}</div>
                        </div>
                        <div style="font-weight:800; font-size:24px; color:#0F172A; margin-top:10px;">{value_str}</div>
                    """, unsafe_allow_html=True)

                    trend_color = "#16A34A" if trend_pct >= 0 else "#DC2626"
                    arrow = "↑" if trend_pct >= 0 else "↓"
                    st.markdown(
                        f'<div style="font-size:11.5px; color:{trend_color}; font-weight:600; margin-top:2px;">'
                        f'{arrow} {abs(trend_pct):.1f}% so với kỳ trước</div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(sparkline(series, spark_color), use_container_width=True,
                                    config={"displayModeBar": False}, key=f"spark_{label}")

        # 4 Thẻ số liệu tổng quan
        c1, c2, c3, c4 = st.columns(4)
        render_metric_card(c1, "📑", "#EEF2FF", "Hóa đơn hạch toán", f"{len(df)}",
                           pct_change(monthly["so_luong"]), monthly["so_luong"], "#4F46E5")
        render_metric_card(c2, "💰", "#ECFDF5", "Tổng giá trị",
                           f"{df['tong_thanh_toan'].sum()/1_000_000:,.1f}M đ",
                           pct_change(monthly["gia_tri"]), monthly["gia_tri"], "#16A34A")
        render_metric_card(c3, "📊", "#F5F3FF", "Thuế GTGT",
                           f"{(df['tong_thanh_toan'].sum() - df['tong_tien_hang'].sum())/1_000_000:,.1f}M đ",
                           pct_change(monthly["thue"]), monthly["thue"], "#7C3AED")
        render_metric_card(c4, "⚡", "#FFFBEB", "Giá trị TB / HĐ",
                           f"{(df['tong_thanh_toan'].sum()/len(df)):,.0f} đ",
                           pct_change(monthly["tb_hoa_don"]), monthly["tb_hoa_don"], "#D97706")

        st.write("")

        # Biểu đồ phân tích chuyên sâu
        col_chart, col_donut = st.columns([1.6, 1])

        with col_chart:
            with st.container(border=True):
                peak = monthly["gia_tri"].max()
                avg = monthly["gia_tri"].mean()

                head_l, head_r = st.columns([2, 1.3])
                with head_l:
                    st.markdown("**Biểu đồ giá trị theo tháng**")
                    st.caption(f"{len(monthly)} tháng gần nhất · triệu đồng")
                with head_r:
                    st.markdown(
                        f'<div style="text-align:right; font-size:11.5px; color:#64748B; padding-top:4px;">'
                        f'Đỉnh: <b style="color:#0F172A;">{peak/1_000_000:,.0f}M đ</b> &nbsp; '
                        f'TB: <b style="color:#0F172A;">{avg/1_000_000:,.0f}M đ</b></div>',
                        unsafe_allow_html=True,
                    )

                gia_tri_m = (monthly["gia_tri"] / 1_000_000).round(1)
                colors = ["#C7D2FE"] * (len(monthly) - 1) + ["#4F46E5"]
                month_labels_vn = monthly["thang"].apply(lambda p: f"T{p.month}/{p.year}")

                fig1 = go.Figure(go.Bar(
                    x=month_labels_vn, y=gia_tri_m,
                    marker_color=colors, marker_cornerradius=6,
                    text=gia_tri_m, textposition="outside",
                ))
                fig1.update_layout(
                    height=280, margin=dict(l=10, r=10, t=25, b=10),
                    plot_bgcolor="white", paper_bgcolor="white",
                    yaxis=dict(showgrid=False, visible=False),
                    xaxis=dict(type="category"),
                )
                st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

        with col_donut:
            with st.container(border=True):
                st.markdown("**Tỷ trọng Tiền hàng & Thuế GTGT**")
                st.caption(f"Kỳ thống kê T{now.month}/{now.year}")

                goods_value = df["tong_tien_hang"].sum()
                vat_value = df["tong_thanh_toan"].sum() - goods_value

                donut = go.Figure(go.Pie(
                    labels=["Tiền hàng", "Thuế GTGT"], values=[goods_value, vat_value],
                    hole=0.68, marker=dict(colors=["#4F46E5", "#F59E0B"]),
                    textinfo="none", hovertemplate="%{label}: %{value:,.0f} đ<extra></extra>",
                ))
                donut.update_layout(
                    height=195, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                    paper_bgcolor="white",
                    annotations=[dict(
                        text=f"{(goods_value+vat_value)/1_000_000:,.1f}M<br><span style='font-size:11px;color:#94A3B8;'>đ</span>",
                        x=0.5, y=0.5, showarrow=False, font=dict(size=17, color="#0F172A"),
                    )],
                )
                st.plotly_chart(donut, use_container_width=True, config={"displayModeBar": False})

                for color, label, val in [("#4F46E5", "Tiền hàng", goods_value), ("#F59E0B", "Thuế GTGT", vat_value)]:
                    pct = (val / (goods_value + vat_value) * 100) if (goods_value + vat_value) else 0
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
                        <span style="width:8px; height:8px; border-radius:50%; background:{color};"></span>
                        <span style="flex:1; font-size:12.5px; color:#1E293B;">{label}</span>
                        <span style="font-size:12.5px; font-weight:700; color:#0F172A;">{val:,.0f} đ</span>
                    </div>
                    """, unsafe_allow_html=True)

        st.write("")
        
        # --- Top Nhà cung cấp ---
        with st.container(border=True):
            st.markdown("**🏆 Top 5 Nhà cung cấp giao dịch lớn nhất**")
            st.caption(f"Theo tổng giá trị thanh toán trong kỳ")

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
                max_val = top_suppliers["tong_tien"].max()
                for i, row in top_suppliers.iterrows():
                    p = (row["tong_tien"] / max_val) * 100
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:14px; padding:10px 0; {'border-top:1px solid #F1F5F9;' if i > 0 else ''}">
                        <div style="width:24px; height:24px; border-radius:6px; background:#EEF2FF; color:#4F46E5; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;">
                            {i+1:02d}
                        </div>
                        <div style="flex:1;">
                            <div style="font-weight:600; color:#0F172A; font-size:13.5px;">{html.escape(str(row['ten_cong_ty_ban']))}</div>
                            <div style="background:#F1F5F9; border-radius:999px; height:5px; margin-top:6px; width:100%;">
                                <div style="background:#4F46E5; height:5px; border-radius:999px; width:{p:.0f}%;"></div>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-weight:700; color:#0F172A; font-size:13.5px;">{row['tong_tien']:,.0f} đ</div>
                            <div style="font-size:11px; color:#94A3B8;">{row['so_luong']} hóa đơn</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# ================= TAB 2: KIỂM TOÁN SAI LỆCH =================
with tab_audit:
    st.markdown("##### 🔍 Báo cáo kiểm tra logic & số học hóa đơn")
    st.caption("Hệ thống tự động quét các điểm bất thường về thuế suất, tổng tiền, ngày tháng hoặc thiếu sót thông tin bắt buộc.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Tổng hồ sơ quét", len(all_invoices))
    m2.metric("Hồ sơ có sai lệch", len(invoices_with_findings))
    m3.metric("Tổng lỗi / cảnh báo", warning_count)

    st.write("")
    if invoices_with_findings:
        st.dataframe(invoices_with_findings, use_container_width=True, hide_index=True)
        st.markdown("""
        <div class="info-bar" style="margin-top:16px;">
            <span>ℹ️</span> 
            <span><b>Lưu ý nghiệp vụ:</b> Các cảnh báo trên chỉ mang tính chất hỗ trợ kiểm tra chéo, không tự động can thiệp sửa đổi dữ liệu gốc của doanh nghiệp.</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="success-notice" style="padding:20px; justify-content:center; text-align:center;">
            ✅ <strong>Tuyệt vời!</strong> Không phát hiện sai lệch số học hay lỗi logic nào theo các quy tắc kiểm tra hiện hành.
        </div>
        """, unsafe_allow_html=True)

# ================= TAB 3: ĐỐI SOÁT TRÙNG LẶP =================
with tab_duplicates:
    st.markdown("##### 🔁 Báo cáo kiểm tra hóa đơn trùng lặp")
    st.caption("Đối soát dựa trên Mã số thuế bên bán và Số hóa đơn kết hợp kiểm tra ngày lập & tổng thanh toán.")

    if duplicate_groups:
        duplicate_rows = []
        for group in duplicate_groups:
            duplicate_rows.append({
                "MST bên bán": group["seller_tax_id"],
                "Số hóa đơn": group["invoice_number"],
                "Các bản ghi liên quan": ", ".join(f"#{invoice.get('id')}" for invoice in group["invoices"]),
                "Ngày lập khớp": "Có" if group["dates_match"] else "Không / Khác nhau",
                "Tổng tiền khớp": "Có" if group["amounts_match"] else "Không / Khác nhau",
                "Đánh giá rủi ro": "Trùng khớp hoàn toàn" if group["exact_match"] else "Nghi vấn trùng lặp",
            })

        dup_c1, dup_c2 = st.columns(2)
        dup_c1.metric("Nhóm nghi vấn trùng", len(duplicate_groups))
        dup_c2.metric("Tổng hóa đơn liên quan", len(duplicate_invoice_ids))
        
        st.write("")
        st.dataframe(duplicate_rows, use_container_width=True, hide_index=True)
    else:
        st.markdown("""
        <div class="success-notice" style="padding:20px; justify-content:center; text-align:center;">
            ✅ <strong>An toàn:</strong> Không phát hiện cặp hóa đơn nào bị trùng lặp số hiệu và mã số thuế bên bán.
        </div>
        """, unsafe_allow_html=True)

# ================= TAB 4: NHẬT KÝ HOẠT ĐỘNG =================
with tab_activity:
    st.markdown("##### ⏱️ Nhật ký tiến trình hệ thống trong ngày")
    st.caption(f"Lịch sử xử lý công việc trực tuyến ngày {now.strftime('%d/%m/%Y')}")

    today_jobs = [
        j for j in get_recent_jobs(limit=100, user_id=USER_ID, is_admin=IS_ADMIN)
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
        st.info("Chưa ghi nhận hoạt động xử lý hóa đơn nào trong ngày hôm nay.")
    else:
        for i, job in enumerate(today_jobs):
            dot = STATUS_DOT.get(job["status"], "#94A3B8")
            text = STATUS_TEXT.get(job["status"], job["status"])
            time_str = job["created_at"].strftime("%H:%M:%S")
            safe_file_name = html.escape(str(job["file_name"] or ""))
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:12px; padding:10px 14px; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; margin-bottom:8px;">
                <span style="width:9px; height:9px; border-radius:50%; background:{dot}; flex-shrink:0;"></span>
                <div style="flex:1; font-weight:600; color:#1E293B; font-size:13.5px;">{safe_file_name}</div>
                <div style="font-size:12px; color:#64748B;">{time_str}</div>
                <div style="font-size:12px; color:{dot}; font-weight:700; background:{dot}15; padding:3px 10px; border-radius:99px; min-width:80px; text-align:center;">{text}</div>
            </div>
            """, unsafe_allow_html=True)