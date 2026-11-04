from pydantic import BaseModel, Field
from typing import List, Optional


class InvoiceItem(BaseModel):
    ten_hang: str = Field(description="Tên hàng hóa/dịch vụ")
    so_luong: float = Field(description="Số lượng")
    don_gia: float = Field(description="Đơn giá")
    thanh_tien: float = Field(description="Thành tiền")


class Invoice(BaseModel):
    ma_so_thue_ban: str = Field(description="Mã số thuế người bán")
    ten_cong_ty_ban: str = Field(description="Tên công ty bán")
    so_hoa_don: Optional[str] = Field(default=None, description="Số hóa đơn")
    ma_so_thue_mua: Optional[str] = Field(default=None, description="Mã số thuế người mua")
    ten_cong_ty_mua: Optional[str] = Field(default=None, description="Tên công ty mua")
    ngay_lap: str = Field(description="Ngày lập hóa đơn")
    danh_sach_mat_hang: List[InvoiceItem] = Field(default_factory=list)
    tong_tien_hang: float = Field(description="Tổng tiền hàng chưa thuế")
    thue_suat_vat: str = Field(description="Thuế suất VAT, ví dụ '8%'")
    tien_thue_vat: float = Field(description="Tiền thuế VAT")
    tong_thanh_toan: float = Field(description="Tổng tiền thanh toán")