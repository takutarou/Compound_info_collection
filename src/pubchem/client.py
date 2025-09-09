"""
PubChem API client for fetching chemical compound information
"""
import time
import urllib.parse
import logging
from typing import List, Dict, Set, Tuple, Optional
import threading

try:
    from itertools import batched
except ImportError:
    from more_itertools import batched

from .utils import safe_get, validate_cas, CAS_RE
from .models import CompoundInfo, CASInfo, SearchResult
from config.settings import (
    CID_LIMIT, CHUNK_SIZE, SLEEP_PROP, SLEEP_CAS, SLEEP_CID, MAX_SYNONYM
)


class PubChemClient:
    """PubChem API client for chemical compound data retrieval"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_cid_from_cas(self, cas_number: str) -> SearchResult:
        """
        CAS番号からCID候補を取得（Compound + Substance検索・効率化版）
        """
        if not validate_cas(cas_number):
            self.logger.warning(f"無効なCAS番号: {cas_number}")
            return SearchResult([], [], False, "invalid")
        
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
        
        # Phase 1: Compound検索
        for endpoint_idx, url in enumerate(compound_endpoints):
            try:
                response = safe_get(url)
                data = response.json()
                
                if "IdentifierList" in data and "CID" in data["IdentifierList"]:
                    cids = data["IdentifierList"]["CID"]
                    self.logger.debug(f"CAS '{cas_cleaned}' Compound検索成功 (endpoint {endpoint_idx+1}): {len(cids)} 件のCID取得")
                    return SearchResult(cids[:CID_LIMIT], [], True, "compound")
                
            except Exception as e:
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                    self.logger.debug(f"CAS '{cas_cleaned}' Compound endpoint {endpoint_idx+1}: データなし (404)")
                else:
                    self.logger.debug(f"CAS '{cas_cleaned}' Compound endpoint {endpoint_idx+1} 失敗: {e}")
                continue
        
        # Phase 2: Substance → CID検索
        for endpoint_idx, url in enumerate(substance_cid_endpoints):
            try:
                response = safe_get(url)
                data = response.json()
                
                if "IdentifierList" in data and "CID" in data["IdentifierList"]:
                    cids = data["IdentifierList"]["CID"]
                    self.logger.debug(f"CAS '{cas_cleaned}' Substance→CID検索成功 (endpoint {endpoint_idx+1}): {len(cids)} 件のCID取得")
                    return SearchResult(cids[:CID_LIMIT], [], True, "substance_cid")
                
            except Exception as e:
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                    self.logger.debug(f"CAS '{cas_cleaned}' Substance→CID endpoint {endpoint_idx+1}: データなし (404)")
                else:
                    self.logger.debug(f"CAS '{cas_cleaned}' Substance→CID endpoint {endpoint_idx+1} 失敗: {e}")
                continue
        
        # Phase 3: SID取得（CIDが見つからない場合）
        for endpoint_idx, url in enumerate(substance_sid_endpoints):
            try:
                response = safe_get(url)
                data = response.json()
                
                if "IdentifierList" in data and "SID" in data["IdentifierList"]:
                    sids = data["IdentifierList"]["SID"]
                    self.logger.debug(f"CAS '{cas_cleaned}' SID検索成功 (endpoint {endpoint_idx+1}): {len(sids)} 件のSID取得")
                    return SearchResult([], sids[:CID_LIMIT], True, "substance_sid")
                
            except Exception as e:
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                    self.logger.debug(f"CAS '{cas_cleaned}' SID endpoint {endpoint_idx+1}: データなし (404)")
                else:
                    self.logger.debug(f"CAS '{cas_cleaned}' SID endpoint {endpoint_idx+1} 失敗: {e}")
                continue
        
        self.logger.info(f"CAS '{cas_cleaned}': 全検索で該当データなし")
        return SearchResult([], [], False, "not_found")
    
    def get_sid_properties(self, sid: int) -> Dict[str, any]:
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
                                    self.logger.debug(f"SID {sid}: SMILES取得 - {label}: {smiles}")
                                
                                # InChI情報も取得
                                elif "INCHI" in label and "value" in prop and "sval" in prop["value"]:
                                    inchi = prop["value"]["sval"]
                                    properties["InChI"] = inchi
                                    self.logger.debug(f"SID {sid}: InChI取得: {inchi}")
                
                # 関連CID取得試行
                try:
                    cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/sid/{sid}/cids/JSON"
                    cid_response = safe_get(cid_url)
                    cid_data = cid_response.json()
                    
                    if "IdentifierList" in cid_data and "CID" in cid_data["IdentifierList"]:
                        related_cids = cid_data["IdentifierList"]["CID"]
                        properties["Related_CIDs"] = related_cids
                        self.logger.debug(f"SID {sid}: 関連CID {related_cids}")
                except:
                    pass
            
            # SIDからSMILESが取得できた場合はログ出力
            if "SMILES" in properties or "IsomericSMILES" in properties:
                self.logger.info(f"SID {sid}: 構造情報取得成功 (SMILES利用可能)")
            
            self.logger.debug(f"SID {sid}: プロパティ取得成功")
            return properties
            
        except Exception as e:
            self.logger.warning(f"SID {sid}: プロパティ取得失敗 - {e}")
            return {}
    
    def get_cas_pairs(self, cid: int) -> List[Tuple[str, str]]:
        """CIDからCAS番号のリスト（preferred + synonym）を取得"""
        pairs = []
        
        # preferred CAS取得
        try:
            rn_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RN/JSON"
            rn_response = safe_get(rn_url)
            rn_data = rn_response.json()
            if "InformationList" in rn_data and "Information" in rn_data["InformationList"]:
                rn = rn_data["InformationList"]["Information"][0]["RN"]
                preferred_cas = [c for c in rn if CAS_RE.match(c)]
                pairs.extend([(c, "preferred") for c in preferred_cas])
                self.logger.debug(f"CID {cid}: {len(preferred_cas)} 件のpreferred CAS取得")
        except Exception as e:
            self.logger.debug(f"CID {cid}: preferred CAS取得失敗 - {e}")
        
        # synonym CAS取得 (最大 MAX_SYNONYM 件)
        if len(pairs) < 1 + MAX_SYNONYM:
            try:
                syn_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
                syn_response = safe_get(syn_url)
                syn_data = syn_response.json()
                if "InformationList" in syn_data and "Information" in syn_data["InformationList"]:
                    syns = syn_data["InformationList"]["Information"][0]["Synonym"]
                    extras = [s for s in syns if CAS_RE.match(s)][:MAX_SYNONYM]
                    pairs.extend([(s, "synonym") for s in extras])
                    self.logger.debug(f"CID {cid}: {len(extras)} 件のsynonym CAS取得")
            except Exception as e:
                self.logger.debug(f"CID {cid}: synonym CAS取得失敗 - {e}")
        
        return pairs
    
    def choose_best_cas(self, cid_dict: Dict[str, List[Tuple[str, str]]], original_cas: str = "") -> Tuple[str, str]:
        """代表CASを選定"""
        # 元のCASが見つかったらそれを優先
        for cid, lst in cid_dict.items():
            for cas, cas_type in lst:
                if cas == original_cas:
                    self.logger.debug(f"CID {cid}: 元のCAS '{cas}' を採用")
                    return cid, cas
        
        # preferredが1件なら採用
        for cid, lst in cid_dict.items():
            pref = [c for c, t in lst if t == "preferred"]
            if len(pref) == 1:
                self.logger.debug(f"CID {cid}: preferred CAS '{pref[0]}' を採用")
                return cid, pref[0]
        
        # 最短文字数のCASを選択
        all_cas = [(c, cid) for cid, v in cid_dict.items() for c, _ in v]
        if not all_cas:
            return "", ""
        
        shortest = min(len(c) for c, _ in all_cas)
        cand = [(c, cid) for c, cid in all_cas if len(c) == shortest]
        cas, cid = min(cand, key=lambda x: int(x[0].split('-')[0]))
        self.logger.debug(f"CID {cid}: 最短CAS '{cas}' を採用")
        return cid, cas
    
    def fetch_properties_batched(self, cids: List[int]) -> Dict[int, dict]:
        """バッチでCIDのプロパティを取得"""
        res = {}
        if not cids:
            return res
        
        prop_url_template = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
                           "{cids}/property/Title,CanonicalSMILES,IsomericSMILES/JSON")
        
        total_chunks = len(list(batched(cids, CHUNK_SIZE)))
        
        self.logger.info(f"プロパティ取得開始: {len(cids)} CID を {total_chunks} バッチで処理")
        
        for chunk_idx, chunk in enumerate(batched(cids, CHUNK_SIZE), 1):
            chunk_list = list(chunk)
            url = prop_url_template.format(cids=",".join(map(str, chunk_list)))
            
            try:
                response = safe_get(url)
                data = response.json()
                if "PropertyTable" in data and "Properties" in data["PropertyTable"]:
                    props = data["PropertyTable"]["Properties"]
                    for p in props:
                        res[p["CID"]] = p
                    self.logger.info(f"バッチ {chunk_idx}/{total_chunks}: {len(props)} 件のプロパティ取得成功")
            except Exception as e:
                self.logger.warning(f"バッチ {chunk_idx}/{total_chunks}: バッチ取得失敗、個別取得にフォールバック - {e}")
                # fallback 個別
                for cid in chunk_list:
                    try:
                        single_response = safe_get(prop_url_template.format(cids=cid))
                        single_data = single_response.json()
                        if "PropertyTable" in single_data and "Properties" in single_data["PropertyTable"]:
                            single = single_data["PropertyTable"]["Properties"][0]
                            res[cid] = single
                            self.logger.debug(f"CID {cid}: 個別プロパティ取得成功")
                    except Exception as single_e:
                        self.logger.warning(f"CID {cid}: 個別プロパティ取得失敗 - {single_e}")
            
            time.sleep(SLEEP_PROP)
        
        self.logger.info(f"プロパティ取得完了: {len(res)} 件成功")
        return res
    
    def fetch_cas_parallel(self, cids: List[int], workers: int = 2) -> Dict[int, List[Tuple[str, str]]]:
        """並列でCIDからCAS情報を取得"""
        if not cids:
            return {}
        
        out, lock = {}, threading.Lock()
        
        def worker(sub):
            for cid in sub:
                try:
                    pairs = self.get_cas_pairs(cid)
                    with lock:
                        out[cid] = pairs
                    self.logger.debug(f"CID {cid}: {len(pairs)} 件のCAS取得完了")
                except Exception as e:
                    self.logger.warning(f"CID {cid}: CAS取得失敗 - {e}")
                time.sleep(SLEEP_CAS)
        
        self.logger.info(f"CAS取得開始: {len(cids)} CID を {workers} スレッドで並列処理")
        
        chunks = list(batched(cids, max(1, len(cids)//workers)))
        threads = [threading.Thread(target=worker, args=(ch,)) for ch in chunks]
        
        for t in threads: 
            t.start()
        for t in threads: 
            t.join()
        
        self.logger.info(f"CAS取得完了: {len(out)} 件成功")
        return out