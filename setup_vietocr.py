import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_original_get = requests.get

def _patched_get(url, **kwargs):
    kwargs["verify"] = False
    return _original_get(url, **kwargs)

requests.get = _patched_get  # chỉ patch tạm trong script này, không ảnh hưởng chương trình chính

from vietocr.tool.config import Cfg
from vietocr.tool.predictor import Predictor

print("Đang tải config...")
config = Cfg.load_config_from_name('vgg_transformer')
config.save('vietocr_config.yml')
print("Đã lưu config -> vietocr_config.yml")

print("Đang tải weights model (có thể mất vài phút)...")
config['device'] = 'cpu'
predictor = Predictor(config)  # bước này tải + cache weights về local
print("Hoàn tất! VietOCR đã sẵn sàng chạy offline.")

requests.get = _original_get  # khôi phục lại hành vi gốc, tránh ảnh hưởng phần còn lại của hệ thống