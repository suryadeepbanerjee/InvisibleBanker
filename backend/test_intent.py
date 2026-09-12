import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.llm.intent import extract_intent

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    queries = [
        "प्रधानमंत्री आवास योजना के बारे में बताओ",
        "My UPI payment failed",
        "I need a loan for my shop"
    ]
    
    for q in queries:
        print(f"\nQuery: {q}")
        res = extract_intent(q)
        print(f"Domain: {res.domain}")
        print(f"Topic: {res.topic}")
        print(f"Task: {res.task}")
        print(f"Loan Amount: {res.loan_amount}")

if __name__ == "__main__":
    main()
