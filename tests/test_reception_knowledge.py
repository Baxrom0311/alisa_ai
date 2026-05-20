"""Tests for reception knowledge base."""

import pytest
from alisa.reception.knowledge import KnowledgeBase


class TestKnowledgeBase:
    """Test knowledge base functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.kb = KnowledgeBase()
    
    def test_find_answer_work_hours(self):
        """Test finding work hours answer."""
        questions = [
            "ish vaqti nima?",
            "working hours",
            "qachon ochiq?",
            "when open",
            "soat nechada ishlaysiz?"
        ]
        
        for question in questions:
            answer = self.kb.find_answer(question)
            assert answer is not None
            assert "9:00-18:00" in answer
    
    def test_find_answer_address(self):
        """Test finding address answer."""
        questions = [
            "manzil qayerda?",
            "address",
            "qayerda joylashgan?",
            "where located"
        ]
        
        for question in questions:
            answer = self.kb.find_answer(question)
            assert answer is not None
            assert "Toshkent" in answer
    
    def test_find_answer_phone(self):
        """Test finding phone answer."""
        questions = [
            "telefon raqam",
            "phone number",
            "aloqa"
        ]
        
        for question in questions:
            answer = self.kb.find_answer(question)
            assert answer is not None
            assert "+998" in answer
    
    def test_find_answer_services(self):
        """Test finding services answer."""
        questions = [
            "nima xizmat qilasiz?",
            "what do you do",
            "faoliyat"
        ]
        
        for question in questions:
            answer = self.kb.find_answer(question)
            assert answer is not None
            assert "AI" in answer
    
    def test_find_answer_no_match(self):
        """Test no match returns None."""
        answer = self.kb.find_answer("random unrelated question")
        assert answer is None
    
    def test_find_answer_empty_question(self):
        """Test empty question returns None."""
        assert self.kb.find_answer("") is None
        assert self.kb.find_answer(None) is None
    
    def test_get_greeting(self):
        """Test greeting message."""
        greeting = self.kb.get_greeting()
        assert greeting is not None
        assert "Assalomu alaykum" in greeting
        assert "Alisa" in greeting
    
    def test_get_default_response(self):
        """Test default response."""
        response = self.kb.get_default_response()
        assert response is not None
        assert "Kechirasiz" in response
