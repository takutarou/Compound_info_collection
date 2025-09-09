"""
PubChem full data client for comprehensive chemical compound information retrieval
"""
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

from .utils import safe_get
from config.settings import SLEEP_CID, OUTPUT_TIMESTAMP_FORMAT
import datetime


class PubChemFullDataClient:
    """PubChemから化合物の完全なデータを取得するクライアント"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_full_compound_data(self, cid: int) -> Optional[Dict]:
        """
        CIDから化合物の完全なJSONデータを取得
        
        Args:
            cid: PubChem Compound ID
            
        Returns:
            化合物の完全なJSONデータ、失敗時はNone
        """
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/JSON"
            self.logger.debug(f"CID {cid}: 全データ取得開始")
            
            response = safe_get(url)
            data = response.json()
            
            # レスポンスの検証
            if "PC_Compounds" in data and len(data["PC_Compounds"]) > 0:
                compound_data = data["PC_Compounds"][0]
                self.logger.debug(f"CID {cid}: 全データ取得成功 ({len(json.dumps(data))} 文字)")
                return data
            else:
                self.logger.warning(f"CID {cid}: データ形式が不正")
                return None
                
        except Exception as e:
            self.logger.error(f"CID {cid}: 全データ取得失敗 - {e}")
            return None
    
    def get_full_substance_data(self, sid: int) -> Optional[Dict]:
        """
        SIDから物質の完全なJSONデータを取得
        
        Args:
            sid: PubChem Substance ID
            
        Returns:
            物質の完全なJSONデータ、失敗時はNone
        """
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/sid/{sid}/JSON"
            self.logger.debug(f"SID {sid}: 全データ取得開始")
            
            response = safe_get(url)
            data = response.json()
            
            # レスポンスの検証
            if "PC_Substances" in data and len(data["PC_Substances"]) > 0:
                self.logger.debug(f"SID {sid}: 全データ取得成功 ({len(json.dumps(data))} 文字)")
                return data
            else:
                self.logger.warning(f"SID {sid}: データ形式が不正")
                return None
                
        except Exception as e:
            self.logger.error(f"SID {sid}: 全データ取得失敗 - {e}")
            return None
    
    def save_individual_compound_files(self, compounds_data: List[Tuple[int, str, str, Dict]], 
                                     output_dir: Path) -> None:
        """
        各化合物の全データを個別JSONファイルに保存
        
        Args:
            compounds_data: (CID/SID, INCI名, CAS番号, 全データ) のリスト
            output_dir: 出力ディレクトリ
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for compound_id, inci_name, cas_number, full_data in compounds_data:
            if full_data is None:
                continue
                
            # ファイル名を安全な形式に変換
            safe_inci_name = self._sanitize_filename(inci_name)
            safe_cas = self._sanitize_filename(cas_number)
            
            filename = f"{compound_id}_{safe_cas}_{safe_inci_name}.json"
            file_path = output_dir / filename
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(full_data, f, ensure_ascii=False, indent=2)
                
                self.logger.info(f"保存完了: {filename} ({len(json.dumps(full_data)):,} 文字)")
                
            except Exception as e:
                self.logger.error(f"ファイル保存失敗 {filename}: {e}")
    
    def create_compound_summary(self, compounds_data: List[Tuple[int, str, str, Dict]], 
                              output_path: Path) -> None:
        """
        化合物データの概要を作成
        
        Args:
            compounds_data: (CID/SID, INCI名, CAS番号, 全データ) のリスト  
            output_path: 概要ファイルのパス
        """
        summary = {
            "metadata": {
                "creation_date": datetime.datetime.now().isoformat(),
                "total_compounds": len(compounds_data),
                "successful_retrievals": sum(1 for _, _, _, data in compounds_data if data is not None)
            },
            "compounds": []
        }
        
        for compound_id, inci_name, cas_number, full_data in compounds_data:
            compound_summary = {
                "compound_id": compound_id,
                "inci_name": inci_name,
                "cas_number": cas_number,
                "data_available": full_data is not None,
                "data_size_chars": len(json.dumps(full_data)) if full_data else 0
            }
            
            # データが存在する場合、基本情報を抽出
            if full_data:
                compound_summary.update(self._extract_basic_info(full_data))
            
            summary["compounds"].append(compound_summary)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"概要ファイル作成完了: {output_path}")
            
        except Exception as e:
            self.logger.error(f"概要ファイル作成失敗: {e}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        ファイル名として安全な文字列に変換
        """
        import re
        # 危険な文字を置換
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 連続するアンダースコアを単一に
        filename = re.sub(r'_+', '_', filename)
        # 先頭・末尾のアンダースコアを除去
        filename = filename.strip('_')
        # 長すぎる場合は切り詰め
        if len(filename) > 100:
            filename = filename[:100]
        return filename or "unnamed"
    
    def _extract_basic_info(self, full_data: Dict) -> Dict:
        """
        全データから基本情報を抽出
        """
        basic_info = {}
        
        try:
            if "PC_Compounds" in full_data:
                compound = full_data["PC_Compounds"][0]
                
                # Molecular formula
                if "props" in compound:
                    for prop in compound["props"]:
                        if "urn" in prop and "label" in prop["urn"]:
                            label = prop["urn"]["label"]
                            if "Molecular Formula" in label and "value" in prop:
                                if "sval" in prop["value"]:
                                    basic_info["molecular_formula"] = prop["value"]["sval"]
                                    break
                
                # Count atoms, bonds etc.
                basic_info["atom_count"] = len(compound.get("atoms", {}).get("element", []))
                if "bonds" in compound:
                    basic_info["bond_count"] = len(compound["bonds"].get("aid1", []))
                
            elif "PC_Substances" in full_data:
                substance = full_data["PC_Substances"][0]
                basic_info["data_type"] = "substance"
                basic_info["source"] = substance.get("source", {}).get("db", {}).get("name", "Unknown")
                
        except Exception as e:
            self.logger.debug(f"基本情報抽出エラー: {e}")
        
        return basic_info