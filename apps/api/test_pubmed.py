from app.services.pubmed_service import search_pubmed

print("Searching for SVT management...")
results = search_pubmed("sinistral portal hypertension management", max_results=3)

for r in results:
    print(f"\nTitle: {r['title']}")
    print(f"Journal: {r['journal']} ({r['year']})")
    print(f"Link: {r['link']}")
