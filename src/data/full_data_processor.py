"""
Full data processing for comprehensive PubChem compound information
"""
import json
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm
import time

from src.pubchem.client import PubChemClient
from src.pubchem.full_data_client import PubChemFullDataClient
from config.settings import OUTPUT_TIMESTAMP_FORMAT, SLEEP_CID


class FullDataProcessor:
    """化合物の完全データ取得と処理を担当するクラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pubchem_client = PubChemClient()
        self.full_data_client = PubChemFullDataClient()
    
    def process_compounds_full_data(self, input_data: List[Dict], output_dir: Path) -> None:
        """
        化合物リストから完全データを取得して個別ファイルに保存
        
        Args:
            input_data: 化合物リスト [{"inci": "name", "cas": "123-45-6", "function": "xxx"}]
            output_dir: 出力ディレクトリ
        """
        self.logger.info(f"化合物完全データ処理開始: {len(input_data)} 件")
        
        # Step 1: CAS番号からCID/SID検索
        self.logger.info("STEP1: CAS番号からCID/SID検索")
        compounds_info = []
        
        for idx, item in enumerate(tqdm(input_data, desc="CID/SID検索")):
            cas_number = item.get("cas", "").strip()
            inci_name = item.get("inci", "").strip()
            
            search_result = self.pubchem_client.get_cid_from_cas(cas_number)
            
            if search_result.cids:
                compound_id = search_result.cids[0]
                data_type = "CID"
                self.logger.debug(f"CAS '{cas_number}' → CID {compound_id}")
            elif search_result.sids:
                compound_id = search_result.sids[0]
                data_type = "SID"
                self.logger.debug(f"CAS '{cas_number}' → SID {compound_id}")
            else:
                self.logger.warning(f"CAS '{cas_number}' 検索失敗")
                compounds_info.append((None, inci_name, cas_number, "NOT_FOUND", None))
                continue
            
            compounds_info.append((compound_id, inci_name, cas_number, data_type, None))
            time.sleep(SLEEP_CID)
        
        # Step 2: 完全データ取得
        self.logger.info("STEP2: 化合物完全データ取得")
        compounds_with_data = []
        
        for compound_id, inci_name, cas_number, data_type, _ in tqdm(compounds_info, desc="完全データ取得"):
            if compound_id is None:
                compounds_with_data.append((None, inci_name, cas_number, None))
                continue
            
            # データ取得
            if data_type == "CID":
                full_data = self.full_data_client.get_full_compound_data(compound_id)
            elif data_type == "SID":
                full_data = self.full_data_client.get_full_substance_data(compound_id)
            else:
                full_data = None
            
            compounds_with_data.append((compound_id, inci_name, cas_number, full_data))
            time.sleep(SLEEP_CID)
        
        # Step 3: データ保存
        self.logger.info("STEP3: データ保存")
        timestamp = datetime.datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
        
        # 個別ファイル保存
        individual_dir = output_dir / f"individual_compounds_{timestamp}"
        self.full_data_client.save_individual_compound_files(compounds_with_data, individual_dir)
        
        # 概要ファイル作成
        summary_path = output_dir / f"compounds_full_data_summary_{timestamp}.json"
        self.full_data_client.create_compound_summary(compounds_with_data, summary_path)
        
        # 統計情報
        self._log_statistics(compounds_with_data, individual_dir, summary_path)
    
    def _log_statistics(self, compounds_data: List[Tuple], individual_dir: Path, summary_path: Path) -> None:
        """処理結果の統計情報をログ出力"""
        total_compounds = len(compounds_data)
        successful_retrievals = sum(1 for _, _, _, data in compounds_data if data is not None)
        failed_retrievals = total_compounds - successful_retrievals
        
        # データサイズ統計
        total_size = sum(len(json.dumps(data)) for _, _, _, data in compounds_data if data is not None)
        avg_size = total_size / successful_retrievals if successful_retrievals > 0 else 0
        
        self.logger.info("✅ 完全データ取得処理完了:")
        self.logger.info(f"  処理対象: {total_compounds} 件")
        self.logger.info(f"  取得成功: {successful_retrievals} 件")
        self.logger.info(f"  取得失敗: {failed_retrievals} 件")
        self.logger.info(f"  成功率: {successful_retrievals/total_compounds*100:.1f}%")
        self.logger.info(f"  平均データサイズ: {avg_size:,.0f} 文字")
        self.logger.info(f"  総データサイズ: {total_size:,} 文字")
        self.logger.info(f"  個別ファイル: {individual_dir}")
        self.logger.info(f"  概要ファイル: {summary_path}")


class FullDataAnalyzer:
    """完全データを解析する機能"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_specific_properties(self, full_data_dir: Path, 
                                   properties_of_interest: List[str]) -> Dict:
        """
        完全データから特定のプロパティを抽出
        
        Args:
            full_data_dir: 完全データが保存されているディレクトリ
            properties_of_interest: 抽出したいプロパティのリスト
            
        Returns:
            抽出されたプロパティの辞書
        """
        self.logger.info(f"プロパティ抽出開始: {full_data_dir}")
        
        extracted_data = {}
        json_files = list(full_data_dir.glob("*.json"))
        
        for json_file in tqdm(json_files, desc="プロパティ抽出"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                compound_id = json_file.stem.split('_')[0]
                extracted_data[compound_id] = self._extract_properties_from_data(
                    data, properties_of_interest
                )
                
            except Exception as e:
                self.logger.error(f"ファイル処理失敗 {json_file}: {e}")
        
        return extracted_data
    
    def _extract_properties_from_data(self, full_data: Dict, 
                                    properties_of_interest: List[str]) -> Dict:
        """
        完全データから指定されたプロパティを抽出する内部メソッド
        """
        extracted = {}
        
        # 実装例：分子量、SMILES、分子式など
        if "Molecular Weight" in properties_of_interest:
            extracted["molecular_weight"] = self._find_property_value(
                full_data, "Molecular Weight"
            )
        
        if "SMILES" in properties_of_interest:
            extracted["smiles"] = self._find_property_value(
                full_data, "SMILES"
            )
        
        if "Molecular Formula" in properties_of_interest:
            extracted["molecular_formula"] = self._find_property_value(
                full_data, "Molecular Formula"
            )
        
        # 他のプロパティも同様に追加可能
        
        return extracted
    
    def _find_property_value(self, data: Dict, property_name: str) -> Optional[str]:
        """
        完全データから特定のプロパティ値を検索
        """
        # PubChemのJSON構造を再帰的に検索する実装
        # 実際の実装では、PubChemの構造に合わせて詳細に実装する必要がある
        return None  # プレースホルダー