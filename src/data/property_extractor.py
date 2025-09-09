"""
Chemical properties extraction from PubChem full data files
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional


class PropertyExtractor:
    """PubChemの完全データから化学物性値を抽出するクラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def extract_properties_from_file(self, file_path: Path) -> Dict[str, str]:
        """
        個別の化合物JSONファイルから指定されたプロパティを抽出
        
        Args:
            file_path: 化合物の完全データJSONファイルのパス
            
        Returns:
            抽出されたプロパティの辞書
        """
        extracted_data = {
            "boiling_point": "",
            "melting_point": "",
            "pka": "",
            "pkb": "",
            "dissociation_constants_name": "",
            "molecular_weight": "",
            "density": "",
            "solubility": "",
            "logp": ""
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Record構造の確認
            if 'Record' not in data:
                self.logger.warning(f"'{file_path.name}' にRecord構造が見つかりません。")
                return extracted_data
                
            record = data['Record']
            
            # 1. Chemical and Physical Properties セクションを探す
            chem_phys_section = self._find_section(record, 'Chemical and Physical Properties')
            if chem_phys_section:
                # Experimental Properties を探索
                experimental_props = self._find_section(chem_phys_section, 'Experimental Properties')
                if experimental_props:
                    self._extract_experimental_properties(experimental_props, extracted_data, file_path.name)
                
                # Computed Properties も探索
                computed_props = self._find_section(chem_phys_section, 'Computed Properties')
                if computed_props:
                    self._extract_computed_properties(computed_props, extracted_data, file_path.name)
            
            # 2. その他のセクションからも情報を抽出
            self._extract_additional_properties(record, extracted_data)
                    
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.logger.error(f"ファイル読み込みエラー {file_path}: {e}")
            raise e
        
        return extracted_data
    
    def _find_section(self, parent_section: Dict, target_heading: str) -> Optional[Dict]:
        """指定されたTOCHeadingのセクションを検索"""
        sections = parent_section.get('Section', [])
        for section in sections:
            if section.get('TOCHeading') == target_heading:
                return section
        return None
    
    def _extract_experimental_properties(self, experimental_section: Dict, extracted_data: Dict, filename: str):
        """Experimental Propertiesセクションから物性値を抽出"""
        self.logger.debug(f"'{filename}' の 'Experimental Properties' を探索中...")
        
        for prop_section in experimental_section.get('Section', []):
            toc_heading = prop_section.get('TOCHeading', '')
            
            # 沸点・融点の抽出
            if toc_heading in ['Boiling Point', 'Melting Point']:
                self.logger.debug(f"  - '{toc_heading}' を発見。")
                value = self._extract_value_from_section(prop_section)
                if value:
                    key_name = toc_heading.replace(" ", "_").lower()
                    extracted_data[key_name] = value
                    self.logger.debug(f"    -> 値を抽出: {value}")
            
            # pKa/pKbの抽出  
            elif toc_heading == 'Dissociation Constants':
                self.logger.debug(f"  - '{toc_heading}' を発見。")
                self._extract_dissociation_constants(prop_section, extracted_data)
            
            # その他の物性値
            elif toc_heading == 'Density':
                value = self._extract_value_from_section(prop_section)
                if value:
                    extracted_data['density'] = value
                    self.logger.debug(f"    -> 密度を抽出: {value}")
                    
            elif toc_heading in ['Solubility', 'Water Solubility']:
                value = self._extract_value_from_section(prop_section)
                if value:
                    extracted_data['solubility'] = value
                    self.logger.debug(f"    -> 溶解度を抽出: {value}")
    
    def _extract_computed_properties(self, computed_section: Dict, extracted_data: Dict, filename: str):
        """Computed Propertiesセクションから計算物性値を抽出"""
        self.logger.debug(f"'{filename}' の 'Computed Properties' を探索中...")
        
        for prop_section in computed_section.get('Section', []):
            toc_heading = prop_section.get('TOCHeading', '')
            
            # 分子量
            if toc_heading in ['Molecular Weight', 'Exact Mass']:
                value = self._extract_value_from_section(prop_section)
                if value and not extracted_data['molecular_weight']:  # 実測値を優先
                    extracted_data['molecular_weight'] = value
                    self.logger.debug(f"    -> 分子量を抽出: {value}")
            
            # LogP
            elif toc_heading in ['XLogP3', 'LogP']:
                value = self._extract_value_from_section(prop_section)
                if value:
                    extracted_data['logp'] = value
                    self.logger.debug(f"    -> LogPを抽出: {value}")
    
    def _extract_additional_properties(self, record: Dict, extracted_data: Dict):
        """その他のセクションから追加プロパティを抽出"""
        # Names and Identifiers セクションからの情報抽出など
        # 必要に応じて拡張
        pass
    
    def _extract_value_from_section(self, section: Dict) -> str:
        """セクションから値を抽出する共通メソッド"""
        for info in section.get('Information', []):
            value_dict = info.get('Value', {})
            value = ""
            unit = ""
            
            if 'StringWithMarkup' in value_dict:
                value = value_dict['StringWithMarkup'][0].get('String', '')
            elif 'Number' in value_dict:
                value = str(value_dict['Number'][0])
            
            if value:
                unit = value_dict.get('Unit', '')
                return f"{value} {unit}".strip()
        
        return ""
    
    def _extract_dissociation_constants(self, section: Dict, extracted_data: Dict):
        """解離定数（pKa/pKb）を抽出"""
        for info in section.get('Information', []):
            value_dict = info.get('Value', {})
            value = ""
            
            if 'StringWithMarkup' in value_dict:
                value = value_dict['StringWithMarkup'][0].get('String', '')
            elif 'Number' in value_dict:
                value = str(value_dict['Number'][0])

            if value:
                name_original = info.get('Name', '')
                name_lower = name_original.lower()
                
                extracted_data['dissociation_constants_name'] = name_original
                
                if 'pkb' in name_lower:
                    extracted_data['pkb'] = value
                    self.logger.debug(f"    -> Name: '{name_original}', pKbとして値を抽出: {value}")
                else:
                    extracted_data['pka'] = value
                    self.logger.debug(f"    -> Name: '{name_original}', pKaとして値を抽出: {value}")
                break
    
    def batch_extract_properties(self, individual_files_dir: Path, 
                               summary_file_path: Path) -> Dict[str, Dict]:
        """
        個別ファイルディレクトリから全化合物の物性値を一括抽出
        
        Args:
            individual_files_dir: 個別化合物ファイルが保存されているディレクトリ
            summary_file_path: 概要ファイル（CIDマッピング用）
            
        Returns:
            CIDをキーとした抽出プロパティの辞書
        """
        self.logger.info(f"物性値一括抽出開始: {individual_files_dir}")
        
        # 概要ファイルからCID情報を読み込み
        cid_mapping = {}
        if summary_file_path.exists():
            with open(summary_file_path, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
                for compound in summary_data.get('compounds', []):
                    cid = compound.get('compound_id')
                    if cid:
                        cid_mapping[str(cid)] = compound
        
        extracted_results = {}
        json_files = list(individual_files_dir.glob('*.json'))
        
        self.logger.info(f"{len(json_files)} 個のファイルを処理します。")
        
        for json_file in json_files:
            try:
                # ファイル名からCIDを抽出
                cid_str = json_file.stem.split('_')[0]
                
                # 物性値抽出
                properties = self.extract_properties_from_file(json_file)
                
                # 基本情報も含める
                result = properties.copy()
                if cid_str in cid_mapping:
                    compound_info = cid_mapping[cid_str]
                    result.update({
                        'compound_id': compound_info.get('compound_id'),
                        'inci_name': compound_info.get('inci_name'),
                        'cas_number': compound_info.get('cas_number'),
                        'record_title': compound_info.get('record_title'),
                        'molecular_formula': compound_info.get('molecular_formula'),
                        'smiles': compound_info.get('smiles')
                    })
                
                extracted_results[cid_str] = result
                
                # 抽出された値の数をカウント
                extracted_count = sum(1 for v in properties.values() if v.strip())
                if extracted_count > 0:
                    self.logger.info(f"CID {cid_str}: {extracted_count} 個のプロパティを抽出")
                else:
                    self.logger.debug(f"CID {cid_str}: 抽出されたプロパティなし")
                    
            except Exception as e:
                self.logger.error(f"ファイル処理失敗 {json_file}: {e}")
        
        self.logger.info(f"物性値抽出完了: {len(extracted_results)} 化合物処理")
        return extracted_results
    
    def save_extracted_properties(self, extracted_data: Dict[str, Dict], 
                                 output_path: Path):
        """抽出された物性値をJSONファイルに保存"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"抽出プロパティ保存完了: {output_path}")
            
        except Exception as e:
            self.logger.error(f"ファイル保存失敗: {e}")