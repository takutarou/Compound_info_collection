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
        CIDから化合物の完全なJSONデータを取得（PubChem View API使用）
        見本データと同じRecord/Section形式で取得
        
        Args:
            cid: PubChem Compound ID
            
        Returns:
            化合物の完全なJSONデータ（Record/Section形式）、失敗時はNone
        """
        try:
            # 正しいPubChem View APIエンドポイント
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
            self.logger.debug(f"CID {cid}: 全データ取得開始 (PubChem View API)")
            
            response = safe_get(url)
            data = response.json()
            
            # Record/Section形式の検証
            if "Record" in data and "RecordNumber" in data["Record"]:
                record_number = data["Record"]["RecordNumber"]
                if record_number == cid:
                    data_size = len(json.dumps(data))
                    self.logger.debug(f"CID {cid}: 全データ取得成功 ({data_size:,} 文字, Record形式)")
                    return data
                else:
                    self.logger.warning(f"CID {cid}: RecordNumber不一致 (期待: {cid}, 実際: {record_number})")
                    return None
            else:
                self.logger.warning(f"CID {cid}: データ形式が不正 (Record形式ではない)")
                return None
                
        except Exception as e:
            self.logger.error(f"CID {cid}: 全データ取得失敗 - {e}")
            return None
    
    def get_full_substance_data(self, sid: int) -> Optional[Dict]:
        """
        SIDから物質の完全なJSONデータを取得（PubChem View API使用）
        
        Args:
            sid: PubChem Substance ID
            
        Returns:
            物質の完全なJSONデータ、失敗時はNone
        """
        try:
            # SID用のPubChem View APIエンドポイント
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/substance/{sid}/JSON"
            self.logger.debug(f"SID {sid}: 全データ取得開始 (PubChem View API)")
            
            response = safe_get(url)
            data = response.json()
            
            # Record形式の検証（SIDの場合も同じ構造）
            if "Record" in data and "RecordNumber" in data["Record"]:
                record_number = data["Record"]["RecordNumber"]
                data_size = len(json.dumps(data))
                self.logger.debug(f"SID {sid}: 全データ取得成功 ({data_size:,} 文字, Record形式)")
                return data
            else:
                self.logger.warning(f"SID {sid}: データ形式が不正 (Record形式ではない)")
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
        全データから基本情報を抽出（Record/Section形式用）
        """
        basic_info = {}
        
        try:
            if "Record" not in full_data:
                return basic_info
                
            record = full_data["Record"]
            basic_info["record_type"] = record.get("RecordType", "Unknown")
            basic_info["record_title"] = record.get("RecordTitle", "No Title")
            
            # Molecular Formulaを検索
            molecular_formula = self._find_section_value(record, "Molecular Formula")
            if molecular_formula:
                basic_info["molecular_formula"] = molecular_formula
            
            # SMILES情報を検索 
            smiles = self._find_section_value(record, "SMILES")
            if smiles:
                basic_info["smiles"] = smiles
                
            # IUPAC Nameを検索
            iupac_name = self._find_section_value(record, "IUPAC Name")
            if iupac_name:
                basic_info["iupac_name"] = iupac_name
                
        except Exception as e:
            self.logger.debug(f"基本情報抽出エラー: {e}")
        
        return basic_info
    
    def _find_section_value(self, record: Dict, target_heading: str) -> Optional[str]:
        """
        Record/Section階層から指定されたTOCHeadingの値を検索
        """
        try:
            sections = record.get("Section", [])
            return self._search_sections_recursive(sections, target_heading)
        except Exception as e:
            self.logger.debug(f"セクション検索エラー ({target_heading}): {e}")
            return None
    
    def _search_sections_recursive(self, sections: List[Dict], target_heading: str) -> Optional[str]:
        """
        Section階層を再帰的に検索してTOCHeadingに一致する値を取得
        """
        for section in sections:
            toc_heading = section.get("TOCHeading", "")
            
            # 目的のセクションが見つかった場合
            if target_heading in toc_heading:
                # Information配列から値を抽出
                for info in section.get("Information", []):
                    value = info.get("Value", {})
                    if "StringWithMarkup" in value and value["StringWithMarkup"]:
                        return value["StringWithMarkup"][0].get("String", "")
                    elif "Number" in value and value["Number"]:
                        return str(value["Number"][0])
            
            # 子セクションがある場合は再帰検索
            if "Section" in section:
                result = self._search_sections_recursive(section["Section"], target_heading)
                if result:
                    return result
        
        return None