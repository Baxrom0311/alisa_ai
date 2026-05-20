"""FAQ knowledge base for reception mode."""

import re
from typing import Optional


class KnowledgeBase:
    """Simple FAQ knowledge base for reception mode."""
    
    def __init__(self):
        self.faq = {
            "ish_vaqti": {
                "patterns": [
                    r"ish\s+vaqti",
                    r"working\s+hours?",
                    r"qachon\s+ochiq",
                    r"when\s+open",
                    r"soat\s+nechada"
                ],
                "answer": "Ish vaqtimiz: dushanba-juma 9:00-18:00, shanba 10:00-15:00. Yakshanba dam olish kuni."
            },
            "manzil": {
                "patterns": [
                    r"manzil",
                    r"address",
                    r"qayerda",
                    r"where\s+located",
                    r"joylashuv"
                ],
                "answer": "Bizning manzilimiz: Toshkent shahar, Chilonzor tumani, Bunyodkor ko'chasi 1-uy."
            },
            "telefon": {
                "patterns": [
                    r"telefon",
                    r"phone",
                    r"raqam",
                    r"number",
                    r"aloqa"
                ],
                "answer": "Telefon raqamimiz: +998 71 123-45-67. Telegram: @alisa_reception"
            },
            "xizmatlar": {
                "patterns": [
                    r"xizmat",
                    r"service",
                    r"nima\s+qilasiz",
                    r"what\s+do\s+you\s+do",
                    r"faoliyat"
                ],
                "answer": "Biz AI va dasturlash bo'yicha xizmatlar ko'rsatamiz: konsalting, dastur yaratish, AI modellari."
            }
        }
    
    def find_answer(self, question: str) -> Optional[str]:
        """Find answer for a question based on patterns."""
        if not question:
            return None
            
        question_lower = question.lower()
        
        for topic, data in self.faq.items():
            for pattern in data["patterns"]:
                if re.search(pattern, question_lower):
                    return data["answer"]
        
        return None
    
    def get_greeting(self) -> str:
        """Get standard greeting message."""
        return "Assalomu alaykum! Alisa reception xizmatiga xush kelibsiz. Sizga qanday yordam bera olaman?"
    
    def get_default_response(self) -> str:
        """Get default response when no FAQ match found."""
        return "Kechirasiz, bu savolingizga javob topa olmadim. Iltimos, boshqa savol bering yoki bizning xodimlarimiz bilan bog'laning."
