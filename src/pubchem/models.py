"""
Data models for PubChem API responses
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CompoundInfo:
    """化合物情報を格納するデータクラス"""
    cid: Optional[int] = None
    sid: Optional[int] = None
    title: Optional[str] = None
    cas: Optional[str] = None
    smiles: Optional[str] = None
    isomeric_smiles: Optional[str] = None
    data_source: Optional[str] = None  # "CID" or "SID"
    original_cas: Optional[str] = None
    inci_name: Optional[str] = None
    function: Optional[str] = None


@dataclass
class CASInfo:
    """CAS番号情報を格納するデータクラス"""
    preferred: List[str]
    synonym: List[str]
    
    def get_all_cas(self) -> List[str]:
        """全てのCAS番号を取得"""
        return self.preferred + self.synonym


@dataclass 
class SearchResult:
    """検索結果を格納するデータクラス"""
    cids: List[int]
    sids: List[int]
    success: bool
    search_type: str  # "compound", "substance_cid", "substance_sid"