"""
PubChem API utilities and helper functions
"""
import re
import time
import logging
from typing import List, Optional
import requests
from config.settings import USER_AGENT, TIMEOUT, MAX_RETRY

# CAS number validation regex
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")


def validate_cas(cas_number: str) -> bool:
    """
    CAS番号の形式を検証
    """
    if not cas_number or cas_number.strip() == "":
        return False
    
    cas_cleaned = cas_number.strip()
    return bool(CAS_RE.match(cas_cleaned))


def safe_get(url: str, stream=False):
    """
    効率的なHTTPリクエスト：
    - 404等の確定的エラーは即座に諦める
    - 一時的エラー（500系、タイムアウト等）のみリトライ
    """
    for i in range(MAX_RETRY):
        try:
            r = requests.get(url, headers=USER_AGENT, timeout=TIMEOUT, stream=stream)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            # HTTPエラーレスポンスがある場合のエラーコード判定
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                
                # 確定的エラー：即座に諦める
                if status_code in [400, 401, 403, 404, 405, 410]:
                    logging.debug(f"確定的エラー {status_code}: 即座に次のエンドポイントへ")
                    raise
                
                # 429 Rate Limit：少し待ってリトライ
                elif status_code == 429:
                    if i < MAX_RETRY - 1:
                        wait_time = 30 + (2 ** i)  # 30, 32, 36, 44秒
                        logging.warning(f"レート制限 (試行{i+1}/{MAX_RETRY}): {wait_time}秒待機")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                
                # 一時的エラー（500系）：リトライ
                elif status_code >= 500:
                    if i < MAX_RETRY - 1:
                        wait_time = 2 ** (i + 1)  # 2, 4, 8秒
                        logging.warning(f"サーバーエラー {status_code} (試行{i+1}/{MAX_RETRY}): {wait_time}秒後リトライ")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                
                # その他のHTTPエラー：リトライ
                else:
                    if i < MAX_RETRY - 1:
                        wait_time = 2 ** (i + 1)
                        logging.warning(f"HTTPエラー {status_code} (試行{i+1}/{MAX_RETRY}): {wait_time}秒後リトライ")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
            
            # ネットワークエラー（タイムアウト、接続エラー等）：リトライ
            else:
                if i < MAX_RETRY - 1:
                    wait_time = 2 ** (i + 1)
                    logging.warning(f"ネットワークエラー (試行{i+1}/{MAX_RETRY}): {e} - {wait_time}秒後リトライ")
                    time.sleep(wait_time)
                    continue
                else:
                    raise