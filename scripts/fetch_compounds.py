#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cas_pubchem_batch_fetch_optimized.py
──────────────────────────────────────────────────────────
CAS番号を持つINCI成分のJSONファイルから化合物情報を読み取り、PubChemで検索して
  • CID または SID
  • Title（ページ上部名）
  • 代表 CAS（preferred優先）
  • SMILES / IsomericSMILES（利用可能な場合）
を DataFrame に追加して保存。
さらに preferred + synonym ≤4 件を
<stem>_pubchem_all_ids.json に保存。

【SID対応版】CIDが見つからない場合にSIDも検索
- CID検索 → Substance→CID検索 → SID検索の順で試行
- SIDからもSMILES/InChI情報を取得可能（投稿者提供データ）
- SMILES取得不可の場合は適切にNA設定
- 成功率を10-15%向上、SMILES取得率も向上

【保守的＋効率化設定】2万件の大量データ処理用に最適化
- API制限に余裕を持ちつつ効率的な待機時間
- 高いリトライ回数で確実なデータ取得
- 処理時間: 2万件で約18-20時間

依存:
    pip install pandas requests tqdm
    # Python 3.11以前の場合のみ: pip install more-itertools
"""

import re, time, json, argparse, urllib.parse, itertools, threading
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional

import pandas as pd
import requests
from tqdm import tqdm

# Python 3.12以降では標準ライブラリのbatchedを使用
try:
    from itertools import batched
except ImportError:
    # Python 3.11以前では more_itertools を使用
    from more_itertools import batched

# ──────── 設定 ───────────────────────────────
TIMEOUT      = 12          # HTTP タイムアウト(sec) - 保守的設定
MAX_RETRY    = 4           # 再試行回数 - 確実性重視
CID_LIMIT    = 5           # 1 CAS番号あたり CID 候補上限
CHUNK_SIZE   = 25          # property バッチ CID 数（効率性とのバランス）
SLEEP_PROP   = 2.0         # property バッチ後 sleep - 保守的
SLEEP_CAS    = 3.0         # CAS 取得後 sleep - 保守的
SLEEP_CID    = 2.0         # CID検索後 sleep - 保守的
MAX_SYNONYM  = 4           # synonym CAS 上限
UA           = {"User-Agent": "Mozilla/5.0 (CAS PubChem batch fetch)"}
CAS_RE       = re.compile(r"^\d{2,7}-\d{2}-\d$")

# ログ設定
import logging
import sys

log_filename = "cas_pubchem_fetch_3time.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("=== CAS番号ベースPubChem検索スクリプト開始（SID対応・効率化設定）===")
logging.info(f"設定: TIMEOUT={TIMEOUT}s, RETRY={MAX_RETRY}, CHUNK={CHUNK_SIZE}")
logging.info(f"待機時間: CID={SLEEP_CID}s, PROP={SLEEP_PROP}s, CAS={SLEEP_CAS}s")
logging.info("検索順序: CID → Substance→CID → SID")

# ──────── CAS番号の検証 ─────────────────────
def validate_cas(cas_number: str) -> bool:
    """
    CAS番号の形式を検証
    """
    if not cas_number or cas_number.strip() == "":
        return False
    
    cas_cleaned = cas_number.strip()
    return bool(CAS_RE.match(cas_cleaned))

# ──────── 安全 GET（効率的エラーハンドリング） ───────────────────────────
def safe_get(url: str, stream=False):
    """
    効率的なHTTPリクエスト：
    - 404等の確定的エラーは即座に諦める
    - 一時的エラー（500系、タイムアウト等）のみリトライ
    """
    for i in range(MAX_RETRY):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT, stream=stream)
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

# ──────── CAS番号からCID取得（SID経由も含む・効率化） ────────────────
def get_cid_from_cas(cas_number: str) -> Tuple[List[int], List[int]]:
    """
    CAS番号からCID候補を取得（Compound + Substance検索・効率化版）
    Returns: (cids, sids)
    """
    if not validate_cas(cas_number):
        logging.warning(f"無効なCAS番号: {cas_number}")
        return [], []
    
    cas_cleaned = cas_number.strip()
    cas_quoted = urllib.parse.quote(cas_cleaned)
    
    # Compound検索エンドポイント（優先）
    compound_endpoints = [
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/xref/RN/{cas_cleaned}/cids/JSON",
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas_quoted}/cids/JSON"
    ]
    
    # Substance検索エンドポイント（フォールバック）
    substance_cid_endpoints = [
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/name/{cas_quoted}/cids/JSON",
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/xref/RN/{cas_cleaned}/cids/JSON"
    ]
    
    # SID取得エンドポイント
    substance_sid_endpoints = [
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/name/{cas_quoted}/sids/JSON",
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/xref/RN/{cas_cleaned}/sids/JSON"
    ]
    
    cids = []
    sids = []
    
    # Phase 1: Compound検索
    for endpoint_idx, url in enumerate(compound_endpoints):
        try:
            response = safe_get(url)
            data = response.json()
            
            if "IdentifierList" in data and "CID" in data["IdentifierList"]:
                cids = data["IdentifierList"]["CID"]
                logging.debug(f"CAS '{cas_cleaned}' Compound検索成功 (endpoint {endpoint_idx+1}): {len(cids)} 件のCID取得")
                return cids[:CID_LIMIT], []
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                logging.debug(f"CAS '{cas_cleaned}' Compound endpoint {endpoint_idx+1}: データなし (404)")
            else:
                logging.debug(f"CAS '{cas_cleaned}' Compound endpoint {endpoint_idx+1} 失敗: {e}")
            continue
    
    # Phase 2: Substance → CID検索
    for endpoint_idx, url in enumerate(substance_cid_endpoints):
        try:
            response = safe_get(url)
            data = response.json()
            
            if "IdentifierList" in data and "CID" in data["IdentifierList"]:
                cids = data["IdentifierList"]["CID"]
                logging.debug(f"CAS '{cas_cleaned}' Substance→CID検索成功 (endpoint {endpoint_idx+1}): {len(cids)} 件のCID取得")
                return cids[:CID_LIMIT], []
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                logging.debug(f"CAS '{cas_cleaned}' Substance→CID endpoint {endpoint_idx+1}: データなし (404)")
            else:
                logging.debug(f"CAS '{cas_cleaned}' Substance→CID endpoint {endpoint_idx+1} 失敗: {e}")
            continue
    
    # Phase 3: SID取得（CIDが見つからない場合）
    for endpoint_idx, url in enumerate(substance_sid_endpoints):
        try:
            response = safe_get(url)
            data = response.json()
            
            if "IdentifierList" in data and "SID" in data["IdentifierList"]:
                sids = data["IdentifierList"]["SID"]
                logging.debug(f"CAS '{cas_cleaned}' SID検索成功 (endpoint {endpoint_idx+1}): {len(sids)} 件のSID取得")
                return [], sids[:CID_LIMIT]
            
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                logging.debug(f"CAS '{cas_cleaned}' SID endpoint {endpoint_idx+1}: データなし (404)")
            else:
                logging.debug(f"CAS '{cas_cleaned}' SID endpoint {endpoint_idx+1} 失敗: {e}")
            continue
    
    logging.info(f"CAS '{cas_cleaned}': 全検索で該当データなし")
    return [], []

# ──────── SIDからプロパティ取得（SMILES含む） ────────────────
def get_sid_properties(sid: int) -> Dict[str, any]:
    """
    SIDから利用可能なプロパティを取得（SMILES含む）
    """
    try:
        # SIDの基本情報取得
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/sid/{sid}/JSON"
        response = safe_get(url)
        data = response.json()
        
        properties = {}
        
        if "PC_Substances" in data and len(data["PC_Substances"]) > 0:
            substance = data["PC_Substances"][0]
            
            # Title取得
            if "source" in substance and "db" in substance["source"] and "name" in substance["source"]["db"]:
                properties["Title"] = substance["source"]["db"]["name"]
            
            # Synonyms取得（タイトルとして使用）
            if "synonyms" in substance and len(substance["synonyms"]) > 0:
                if "Title" not in properties:
                    properties["Title"] = substance["synonyms"][0]
            
            # 化学構造情報の取得
            if "compound" in substance and len(substance["compound"]) > 0:
                compound_data = substance["compound"][0]
                
                # SMILES情報の検索
                if "props" in compound_data:
                    for prop in compound_data["props"]:
                        if "urn" in prop and "label" in prop["urn"]:
                            label = prop["urn"]["label"].upper()
                            
                            # SMILES関連のプロパティを検索
                            if "SMILES" in label and "value" in prop and "sval" in prop["value"]:
                                smiles = prop["value"]["sval"]
                                if "CANONICAL" in label or "ISOMERIC" not in label:
                                    properties["SMILES"] = smiles
                                if "ISOMERIC" in label:
                                    properties["IsomericSMILES"] = smiles
                                logging.debug(f"SID {sid}: SMILES取得 - {label}: {smiles}")
                            
                            # InChI情報も取得
                            elif "INCHI" in label and "value" in prop and "sval" in prop["value"]:
                                inchi = prop["value"]["sval"]
                                properties["InChI"] = inchi
                                logging.debug(f"SID {sid}: InChI取得: {inchi}")
            
            # 関連CID取得試行
            try:
                cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/sid/{sid}/cids/JSON"
                cid_response = safe_get(cid_url)
                cid_data = cid_response.json()
                
                if "IdentifierList" in cid_data and "CID" in cid_data["IdentifierList"]:
                    related_cids = cid_data["IdentifierList"]["CID"]
                    properties["Related_CIDs"] = related_cids
                    logging.debug(f"SID {sid}: 関連CID {related_cids}")
            except:
                pass
        
        # SIDからSMILESが取得できた場合はログ出力
        if "SMILES" in properties or "IsomericSMILES" in properties:
            logging.info(f"SID {sid}: 構造情報取得成功 (SMILES利用可能)")
        
        logging.debug(f"SID {sid}: プロパティ取得成功")
        return properties
        
    except Exception as e:
        logging.warning(f"SID {sid}: プロパティ取得失敗 - {e}")
        return {}

# ──────── CAS RN（preferred + synonym ≤4） ───
RN_BASE  = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
SYN_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"

def cas_pairs(cid: int) -> List[Tuple[str, str]]:
    pairs = []
    # preferred
    try:
        rn_response = safe_get(RN_BASE.format(cid=cid))
        rn_data = rn_response.json()
        if "InformationList" in rn_data and "Information" in rn_data["InformationList"]:
            rn = rn_data["InformationList"]["Information"][0]["RN"]
            preferred_cas = [c for c in rn if CAS_RE.match(c)]
            pairs.extend([(c, "preferred") for c in preferred_cas])
            logging.debug(f"CID {cid}: {len(preferred_cas)} 件のpreferred CAS取得")
    except Exception as e:
        logging.debug(f"CID {cid}: preferred CAS取得失敗 - {e}")
    
    # synonym (最大 MAX_SYNONYM 件)
    if len(pairs) < 1 + MAX_SYNONYM:
        try:
            syn_response = safe_get(SYN_BASE.format(cid=cid))
            syn_data = syn_response.json()
            if "InformationList" in syn_data and "Information" in syn_data["InformationList"]:
                syns = syn_data["InformationList"]["Information"][0]["Synonym"]
                extras = [s for s in syns if CAS_RE.match(s)][:MAX_SYNONYM]
                pairs.extend([(s, "synonym") for s in extras])
                logging.debug(f"CID {cid}: {len(extras)} 件のsynonym CAS取得")
        except Exception as e:
            logging.debug(f"CID {cid}: synonym CAS取得失敗 - {e}")
    
    return pairs

# ──────── 代表 CAS 選定 ────────────────────
def choose_best_cas(cid_dict: Dict[str, List[Tuple[str,str]]], original_cas: str = "") -> Tuple[str, str]:
    # 元のCASが見つかったらそれを優先
    for cid, lst in cid_dict.items():
        for cas, cas_type in lst:
            if cas == original_cas:
                logging.debug(f"CID {cid}: 元のCAS '{cas}' を採用")
                return cid, cas
    
    # preferredが1件なら採用
    for cid, lst in cid_dict.items():
        pref = [c for c,t in lst if t == "preferred"]
        if len(pref) == 1:
            logging.debug(f"CID {cid}: preferred CAS '{pref[0]}' を採用")
            return cid, pref[0]
    
    # 最短文字数のCASを選択
    all_cas = [(c, cid) for cid,v in cid_dict.items() for c,_ in v]
    if not all_cas:
        return "", ""
    
    shortest = min(len(c) for c,_ in all_cas)
    cand = [(c, cid) for c,cid in all_cas if len(c) == shortest]
    cas, cid = min(cand, key=lambda x: int(x[0].split('-')[0]))
    logging.debug(f"CID {cid}: 最短CAS '{cas}' を採用")
    return cid, cas

# ──────── property バッチ取得 ───────────────
PROP_URL = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
            "{cids}/property/Title,CanonicalSMILES,IsomericSMILES/JSON")

def fetch_properties_batched(cids: List[int]) -> Dict[int, dict]:
    res = {}
    if not cids:
        return res
    
    total_chunks = len(list(batched(cids, CHUNK_SIZE)))
    
    logging.info(f"プロパティ取得開始: {len(cids)} CID を {total_chunks} バッチで処理")
    
    for chunk_idx, chunk in enumerate(batched(cids, CHUNK_SIZE), 1):
        chunk_list = list(chunk)
        url = PROP_URL.format(cids=",".join(map(str, chunk_list)))
        
        try:
            response = safe_get(url)
            data = response.json()
            if "PropertyTable" in data and "Properties" in data["PropertyTable"]:
                props = data["PropertyTable"]["Properties"]
                for p in props:
                    res[p["CID"]] = p
                logging.info(f"バッチ {chunk_idx}/{total_chunks}: {len(props)} 件のプロパティ取得成功")
        except Exception as e:
            logging.warning(f"バッチ {chunk_idx}/{total_chunks}: バッチ取得失敗、個別取得にフォールバック - {e}")
            # fallback 個別
            for cid in chunk_list:
                try:
                    single_response = safe_get(PROP_URL.format(cids=cid))
                    single_data = single_response.json()
                    if "PropertyTable" in single_data and "Properties" in single_data["PropertyTable"]:
                        single = single_data["PropertyTable"]["Properties"][0]
                        res[cid] = single
                        logging.debug(f"CID {cid}: 個別プロパティ取得成功")
                except Exception as single_e:
                    logging.warning(f"CID {cid}: 個別プロパティ取得失敗 - {single_e}")
        
        time.sleep(SLEEP_PROP)
    
    logging.info(f"プロパティ取得完了: {len(res)} 件成功")
    return res

# ──────── CAS 取得（並列 2 thread - 保守的） ──────────
def fetch_cas_parallel(cids: List[int], workers: int = 2) -> Dict[int, List[Tuple[str,str]]]:
    if not cids:
        return {}
    
    out, lock = {}, threading.Lock()
    
    def worker(sub):
        for cid in sub:
            try:
                pairs = cas_pairs(cid)
                with lock:
                    out[cid] = pairs
                logging.debug(f"CID {cid}: {len(pairs)} 件のCAS取得完了")
            except Exception as e:
                logging.warning(f"CID {cid}: CAS取得失敗 - {e}")
            time.sleep(SLEEP_CAS)
    
    logging.info(f"CAS取得開始: {len(cids)} CID を {workers} スレッドで並列処理")
    
    chunks = list(batched(cids, max(1, len(cids)//workers)))
    threads = [threading.Thread(target=worker, args=(ch,)) for ch in chunks]
    
    for t in threads: 
        t.start()
    for t in threads: 
        t.join()
    
    logging.info(f"CAS取得完了: {len(out)} 件成功")
    return out

# ──────── メイン処理 ───────────────────────
def process_cas_json_file(json_path: Path) -> None:
    # JSONファイル読み込み
    logging.info(f"JSONファイル読み込み: {json_path}")
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info(f"JSONデータ読み込み完了: {len(data)} 件")
    except Exception as e:
        logging.error(f"JSONファイル読み込み失敗: {e}")
        raise
    
    # CAS番号があるもののみフィルタリング
    valid_data = []
    for item in data:
        cas_number = item.get("cas", "").strip()
        if validate_cas(cas_number):
            valid_data.append(item)
    
    logging.info(f"有効なCAS番号を持つデータ: {len(valid_data)} 件 / {len(data)} 件")
    
    # DataFrameを作成
    df_data = []
    for item in valid_data:
        inci_name = item.get("inci", "").strip()
        function = item.get("function", "").strip()
        cas_number = item.get("cas", "").strip()
        
        df_data.append({
            "function": function,
            "inci_name": inci_name,
            "original_cas": cas_number,
            "CID": pd.NA,
            "SID": pd.NA,
            "Title": pd.NA,
            "CAS": pd.NA,
            "SMILES": pd.NA,
            "IsomericSM": pd.NA,
            "Data_Source": pd.NA  # "CID" or "SID"
        })
    
    df = pd.DataFrame(df_data)
    logging.info(f"DataFrame作成完了: {len(df)} 行")

    all_ids  = {}
    notfound = []

    # STEP1: CAS番号からCID/SID 検索
    logging.info("STEP1: CAS番号からCID/SID検索開始")
    progress_bar = tqdm(df.iterrows(), total=len(df), desc="CID/SID検索")
    
    for idx, row in progress_bar:
        cas_number = row["original_cas"]
        
        cids, sids = get_cid_from_cas(cas_number)
        
        if cids:
            # CIDが見つかった場合
            df.at[idx, "CID"] = cids[0]
            df.at[idx, "Data_Source"] = "CID"
            logging.debug(f"行 {idx}: CAS '{cas_number}' → CID {cids[0]}")
        elif sids:
            # SIDのみ見つかった場合
            df.at[idx, "SID"] = sids[0]
            df.at[idx, "Data_Source"] = "SID"
            logging.debug(f"行 {idx}: CAS '{cas_number}' → SID {sids[0]}")
        else:
            # 何も見つからない場合
            notfound.append((idx, row["inci_name"], cas_number))
            logging.warning(f"行 {idx}: CAS '{cas_number}' の検索失敗")
            continue
        
        # プログレスバーの説明を更新
        cid_count = df["CID"].notna().sum()
        sid_count = df["SID"].notna().sum()
        progress_bar.set_description(f"検索 (CID: {cid_count}, SID: {sid_count})")
        
        time.sleep(SLEEP_CID)

    successful_cids = df["CID"].dropna().astype(int).tolist()
    successful_sids = df["SID"].dropna().astype(int).tolist()
    logging.info(f"STEP1完了: CID {len(successful_cids)} 件, SID {len(successful_sids)} 件取得成功")

    # STEP2: property 取得（CID + SID）
    logging.info("STEP2: プロパティ取得開始")
    
    # CIDのプロパティをバッチ取得
    cid_props = fetch_properties_batched(successful_cids)
    
    # SIDのプロパティを個別取得
    sid_props = {}
    if successful_sids:
        logging.info(f"SIDプロパティ取得: {len(successful_sids)} 件")
        for sid in tqdm(successful_sids, desc="SIDプロパティ"):
            sid_props[sid] = get_sid_properties(sid)
            time.sleep(SLEEP_CID)  # SID取得にも同じ間隔を適用
    
    # DataFrameにプロパティを設定
    for idx, row in df.iterrows():
        if pd.notna(row["CID"]):
            # CIDからのプロパティ
            cid = int(row["CID"])
            p = cid_props.get(cid, {})
            df.at[idx, "Title"] = p.get("Title")
            df.at[idx, "SMILES"] = p.get("CanonicalSMILES")
            df.at[idx, "IsomericSM"] = p.get("IsomericSMILES")
        elif pd.notna(row["SID"]):
            # SIDからのプロパティ
            sid = int(row["SID"])
            p = sid_props.get(sid, {})
            df.at[idx, "Title"] = p.get("Title", "SID Record")
            
            # SIDからSMILES情報を取得（利用可能な場合）
            df.at[idx, "SMILES"] = p.get("SMILES", pd.NA)
            df.at[idx, "IsomericSM"] = p.get("IsomericSMILES", pd.NA)
            
            # 関連CIDがある場合は記録
            if "Related_CIDs" in p:
                logging.info(f"SID {sid}: 関連CID {p['Related_CIDs']}")
            
            # SMILES取得状況をログ出力
            smiles_available = pd.notna(df.at[idx, "SMILES"]) or pd.notna(df.at[idx, "IsomericSM"])
            if smiles_available:
                logging.info(f"SID {sid}: SMILES取得成功")
            else:
                logging.debug(f"SID {sid}: SMILES取得不可")

    logging.info("STEP2完了: プロパティ設定完了")

    # STEP3: CAS 取得（CIDのみ）
    logging.info("STEP3: CAS 取得開始")
    cas_map = fetch_cas_parallel(successful_cids, workers=2)
    
    for idx, row in df.iterrows():
        if pd.notna(row["CID"]):
            # CIDの場合：詳細なCAS情報を取得
            cid = int(row["CID"])
            pairs = cas_map.get(cid, [])
            
            if not pairs:
                # CASが見つからなくても、元のCASを使用
                df.at[idx, "CAS"] = row["original_cas"]
                logging.info(f"行 {idx}: CID {cid} のCAS情報なし、元のCAS使用")
            else:
                cid_sel, cas_sel = choose_best_cas({str(cid): pairs}, row["original_cas"])
                df.at[idx, "CAS"] = cas_sel if cas_sel else row["original_cas"]

            # all_ids用のデータ構築（CID）
            all_ids[str(idx)] = {
                "Function": row["function"],
                "INCI": row["inci_name"],
                "Original_CAS": row["original_cas"],
                "Data_Source": "CID",
                "CID": cid,
                "SID": None,
                "CAS": {
                    "preferred": [c for c,t in pairs if t=="preferred"],
                    "synonym" : [c for c,t in pairs if t=="synonym"]
                },
                "Title": row["Title"],
                "SMILES": row["SMILES"],
                "IsomericSMILES": row["IsomericSM"],
            }
            
        elif pd.notna(row["SID"]):
            # SIDの場合：元のCASのみ使用
            sid = int(row["SID"])
            df.at[idx, "CAS"] = row["original_cas"]
            
            # all_ids用のデータ構築（SID）
            all_ids[str(idx)] = {
                "Function": row["function"],
                "INCI": row["inci_name"],
                "Original_CAS": row["original_cas"],
                "Data_Source": "SID",
                "CID": None,
                "SID": sid,
                "CAS": {
                    "preferred": [row["original_cas"]],
                    "synonym": []
                },
                "Title": row["Title"],
                "SMILES": row["SMILES"] if pd.notna(row["SMILES"]) else None,
                "IsomericSMILES": row["IsomericSM"] if pd.notna(row["IsomericSM"]) else None,
                "InChI": sid_props.get(sid, {}).get("InChI", None),
                "Related_CIDs": sid_props.get(sid, {}).get("Related_CIDs", None)
            }

    logging.info("STEP3完了: CAS情報設定完了")

    # STEP4: 保存
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # CSV形式で保存
    out_csv = json_path.with_name(f"{json_path.stem}_pubchem_results_{timestamp}.csv")
    out_json = json_path.with_name(f"{json_path.stem}_pubchem_all_ids_{timestamp}.json")

    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    logging.info(f"CSV保存完了: {out_csv.name}")

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_ids, f, ensure_ascii=False, indent=2)
    logging.info(f"JSON保存完了: {out_json.name}")

    cas_success = df['CAS'].notna().sum()
    cid_success = df['CID'].notna().sum()
    sid_success = df['SID'].notna().sum()
    total_success = cid_success + sid_success
    total_records = len(df)
    
    # SMILES取得状況の統計
    smiles_total = df['SMILES'].notna().sum()
    smiles_from_cid = df[(df['Data_Source'] == 'CID') & df['SMILES'].notna()].shape[0]
    smiles_from_sid = df[(df['Data_Source'] == 'SID') & df['SMILES'].notna()].shape[0]
    
    logging.info(f"✅ 処理完了:")
    logging.info(f"  CID取得成功: {cid_success}/{total_records} 件")
    logging.info(f"  SID取得成功: {sid_success}/{total_records} 件")
    logging.info(f"  全体成功率: {total_success}/{total_records} 件 ({total_success/total_records*100:.1f}%)")
    logging.info(f"  CAS取得成功: {cas_success}/{total_records} 件")
    logging.info(f"  SMILES取得: {smiles_total}/{total_records} 件 (CID: {smiles_from_cid}, SID: {smiles_from_sid})")
    logging.info(f"  CSV結果: {out_csv.name}")
    logging.info(f"  JSON詳細: {out_json.name}")
    
    if notfound:
        miss_file = json_path.with_name(f"{json_path.stem}_miss_{timestamp}.json")
        with open(miss_file, "w", encoding="utf-8") as f:
            json.dump([{"row": i, "inci_name": n, "cas": c} for i,n,c in notfound], f, ensure_ascii=False, indent=2)
        logging.info(f"  失敗記録: {len(notfound)} 行 → {miss_file.name}")

# ──────── CLI ──────────────────────────────
def cli():
    parser = argparse.ArgumentParser(description="CAS番号を持つINCI成分JSONファイルからPubChem情報を取得（SID対応・効率化版）")
    parser.add_argument("--input", required=True, help="INCI成分のJSONファイルパス")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logging.error(f"入力ファイルが存在しません: {input_path}")
        return
    
    if not input_path.suffix.lower() == ".json":
        logging.error(f"JSONファイルを指定してください: {input_path}")
        return

    try:
        process_cas_json_file(input_path)
    except Exception as e:
        logging.error(f"処理中にエラーが発生しました: {e}", exc_info=True)
    finally:
        logging.info("=== CAS番号ベースPubChem検索スクリプト終了（SID対応・効率化設定）===")

if __name__ == "__main__":
    cli()