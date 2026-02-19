import logging
from typing import List, Dict, Any
from Bio import Entrez

# Always identify yourself to NCBI
Entrez.email = "residency.platform@example.com"
Entrez.tool = "ResidencyPlatformThesis"

logger = logging.getLogger(__name__)

def search_pubmed(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search PubMed for papers matching the query.
    Returns a list of dictionaries with title, abstract, authors, journal, year, and link.
    """
    try:
        # 1. Search for IDs
        handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="relevance")
        record = Entrez.read(handle)
        handle.close()
        
        id_list = record["IdList"]
        if not id_list:
            return []

        # 2. Fetch Details
        handle = Entrez.efetch(db="pubmed", id=id_list, rettype="medline", retmode="text")
        # fast parsing of medline format
        from Bio import Medline
        records = Medline.parse(handle)
        
        results = []
        for r in records:
            title = r.get("TI", "No Title")
            abstract = r.get("AB", "No Abstract")
            authors = r.get("AU", [])
            journal = r.get("TA", "Unknown Journal")
            year = r.get("DP", "Unknown Year").split(" ")[0] # usually YYYY Mon DD
            pmid = r.get("PMID", "")
            
            results.append({
                "title": title,
                "abstract": abstract,
                "authors": ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""),
                "journal": journal,
                "year": year,
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            })
            
        handle.close()
        return results

    except Exception as e:
        logger.error(f"PubMed Search Failed: {e}")
        return []
