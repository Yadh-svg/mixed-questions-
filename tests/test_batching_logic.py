import unittest
from collections import defaultdict
import logging

# Mock logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock the function first (or import it if I was editing existing file, but I'll paste the intended logic here for TDD then move it)
# Actually, better to import the function from batch_processor.py and test it.
# But since I haven't written it yet, I will write the TEST expecting the new behavior.

import logging
import sys
import os

# Add parent directory to path to allow importing from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_processor import group_questions_by_type_and_topic

class TestBatchingLogic(unittest.TestCase):
    
    def test_basic_grouping(self):
        """Test simple grouping without special batching requirements (sanity check)"""
        questions = [
            {'type': 'MCQ', 'topic': 'A'},
            {'type': 'MCQ', 'topic': 'B'}
        ]
        result = group_questions_by_type_and_topic(questions)
        self.assertIn('MCQ', result)
        self.assertEqual(len(result['MCQ']), 2)

    def test_priority_packing(self):
        """
        User Scenario:
        4 of topic A
        6 of topic B
        2 of topic C
        
        Expected:
        Batch 1: 4 A (Full batch)
        Batch 2: 4 B (Full batch)
        Batch 3: 2 B + 2 C (Mixed remainder)
        """
        questions = []
        # 4 Topic A
        for i in range(4): questions.append({'type': 'MCQ', 'topic': 'Topic A', 'id': f'A{i}'})
        # 6 Topic B
        for i in range(6): questions.append({'type': 'MCQ', 'topic': 'Topic B', 'id': f'B{i}'})
        # 2 Topic C
        for i in range(2): questions.append({'type': 'MCQ', 'topic': 'Topic C', 'id': f'C{i}'})
        
        # Shuffle input to prove sorting works? 
        # The function should handle unsorted input.
        import random
        random.shuffle(questions)
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        self.assertEqual(len(result_list), 12)
        
        # Check Batch 1 (Indices 0-3)
        # Should be 4 of same topic (most likely A or B depending on which was picked first)
        # But wait, 6 Topic B -> 1 Full Batch (4) + 2 Remainder.
        # 4 Topic A -> 1 Full Batch (4) + 0 Remainder.
        # The logic should prioritize Full Batches.
        
        batch1 = result_list[0:4]
        batch2 = result_list[4:8]
        batch3 = result_list[8:12]
        
        # Verify Batch 1 is pure
        topics1 = {q['topic'] for q in batch1}
        self.assertEqual(len(topics1), 1, f"Batch 1 should be pure, got {topics1}")
        
        # Verify Batch 2 is pure
        topics2 = {q['topic'] for q in batch2}
        self.assertEqual(len(topics2), 1, f"Batch 2 should be pure, got {topics2}")
        
        # Verify Batch 3 is mixed (Remaining 2 B and 2 C)
        topics3 = {q['topic'] for q in batch3}
        self.assertTrue('Topic C' in topics3)
        # If A was Batch 1, assignments:
        # A: 4 consumed.
        # B: 6 total -> 4 consumed in pure batch, 2 left.
        # C: 2 total -> 2 left.
        # Remainder pool: 2 B, 2 C.
        # Mixed Batch: 2 B + 2 C.
        self.assertEqual(len(batch3), 4)

    def test_fragmented_remainders(self):
        """
        3 Topic A
        3 Topic B
        2 Topic C
        Total 8.
        
        No full batches of 4.
        Should pack optimally? Or just greedy?
        The user said "put that together as a batch".
        
        Ideally:
        Batch 1: 3 A + 1 B
        Batch 2: 2 B + 2 C
        OR
        Batch 1: 3 A + 1 C
        Batch 2: 3 B + 1 C
        
        My plan was: Extract Full Batches of 4 FIRST.
        Then pool ALL remainders.
        Then chunk remainders into 4s.
        
        So:
        Remainders: 3 A, 3 B, 2 C.
        Pool order acts as 'First Come First Serve' or sorted?
        If sorted/grouped: A, A, A, B, B, B, C, C
        Batch 1: A A A B
        Batch 2: B B C C
        """
        questions = []
        for i in range(3): questions.append({'type': 'MCQ', 'topic': 'A', 'id': f'A{i}'})
        for i in range(3): questions.append({'type': 'MCQ', 'topic': 'B', 'id': f'B{i}'})
        for i in range(2): questions.append({'type': 'MCQ', 'topic': 'C', 'id': f'C{i}'})
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        self.assertEqual(len(result_list), 8)
        
        # Check integrity
        all_ids = {q['id'] for q in result_list}
        self.assertEqual(len(all_ids), 8)
        
    def test_single_batch_preservation(self):
        """
        User Request: If questions fit in a single batch, DO NOT sort.
        Input: [Topic B, Topic A] (Total 2, Batch Size 4)
        Expected: [Topic B, Topic A] (Order preserved)
        """
        questions = [
            {'type': 'MCQ', 'topic': 'B', 'id': '1'},
            {'type': 'MCQ', 'topic': 'A', 'id': '2'}
        ]
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        self.assertEqual(len(result_list), 2)
        self.assertEqual(result_list[0]['topic'], 'B')
        self.assertEqual(result_list[1]['topic'], 'A')


    def test_smart_preservation_good_split(self):
        """
        Input: [4 Topic A], [4 Topic B] -> Total 8
        Batches are already perfect. Should Preserve Order.
        """
        questions = []
        for i in range(4): questions.append({'type': 'MCQ', 'topic': 'A', 'id': f'A{i}'})
        for i in range(4): questions.append({'type': 'MCQ', 'topic': 'B', 'id': f'B{i}'})
        
        # User input order: AAAA BBBB
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        self.assertEqual(len(result_list), 8)
        # Check integrity: First 4 should be A
        for i in range(4): self.assertEqual(result_list[i]['topic'], 'A')
        # Last 4 should be B
        for i in range(4, 8): self.assertEqual(result_list[i]['topic'], 'B')

    def test_smart_preservation_distinct(self):
        """
        Input: [A, B, C, D], [E, F, G, H]
        All distinct. No duplicate topics across batches to worry about.
        Should Preserve Order (don't group by alphabetic topic).
        """
        topics = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        questions = [{'type': 'MCQ', 'topic': t, 'id': t} for t in topics]
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        # Expect exact order match
        for i, q in enumerate(result_list):
            self.assertEqual(q['topic'], topics[i])

    def test_smart_preservation_bad_split_fix(self):
        """
        Input: [A, A, B, B], [A, A, C, C]
        Topic A is split 2 and 2 across batches.
        Inefficient! Should Reorder to [A, A, A, A], [B, B, C, C].
        """
        questions = []
        # Batch 1 input
        questions.append({'type': 'MCQ', 'topic': 'A', 'id': 'A1'})
        questions.append({'type': 'MCQ', 'topic': 'A', 'id': 'A2'})
        questions.append({'type': 'MCQ', 'topic': 'B', 'id': 'B1'})
        questions.append({'type': 'MCQ', 'topic': 'B', 'id': 'B2'})
        # Batch 2 input
        questions.append({'type': 'MCQ', 'topic': 'A', 'id': 'A3'})
        questions.append({'type': 'MCQ', 'topic': 'A', 'id': 'A4'})
        questions.append({'type': 'MCQ', 'topic': 'C', 'id': 'C1'})
        questions.append({'type': 'MCQ', 'topic': 'C', 'id': 'C2'})
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        # Check Batch 1 (First 4)
        # Should contain all 4 As
        batch1_topics = [q['topic'] for q in result_list[:4]]
        self.assertEqual(batch1_topics.count('A'), 4, f"Should group A together, got {batch1_topics}")
        
    def test_smart_preservation_necessary_split(self):
        """
        Input: [4 'A'], [2 'A', 2 'B']
        Total 6 'A'. 
        Batch 1 has 4 'A'. Batch 2 has 2 'A'.
        This split is NECESSARY because Batch 1 is saturated.
        Should Preserve Order (or reordering yields same result).
        """
        questions = []
        for i in range(6): questions.append({'type': 'MCQ', 'topic': 'A', 'id': f'A{i}'})
        for i in range(2): questions.append({'type': 'MCQ', 'topic': 'B', 'id': f'B{i}'})
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        # Batch 1 should be all A
        b1 = [q['topic'] for q in result_list[:4]]
        self.assertEqual(b1.count('A'), 4)
        
        # Batch 2 should be mixed
        b2 = [q['topic'] for q in result_list[4:]]
        self.assertEqual(b2.count('A'), 2)
        self.assertEqual(b2.count('B'), 2)

    def test_topic_normalization(self):
        """
        Input: 4 variations of the same topic.
        'Topic A', '  Topic A  ', 'Topic   A', 'topic a'
        Should be grouped as ONE topic and form a single pure batch.
        """
        questions = [
            {'type': 'MCQ', 'topic': 'Topic A', 'id': '1'},
            {'type': 'MCQ', 'topic': '  Topic A  ', 'id': '2'},
            {'type': 'MCQ', 'topic': 'Topic   A', 'id': '3'},
            {'type': 'MCQ', 'topic': 'topic a', 'id': '4'}
        ]
        
        result_map = group_questions_by_type_and_topic(questions)
        result_list = result_map['MCQ']
        
        # Should be efficient (all same topic -> 1 batch)
        # Check that we have 4 items
        self.assertEqual(len(result_list), 4)


