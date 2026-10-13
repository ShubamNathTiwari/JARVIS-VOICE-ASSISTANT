from rag import retrieve

while True:
    q = input("\nAsk (or type quit): ")
    if q.lower() in ("quit", "exit"):
        break
    results = retrieve(q)
    if not results:
        print("Nothing relevant found.")
    for chunk, score in results:
        print(f"{score:.2f} | {chunk}")