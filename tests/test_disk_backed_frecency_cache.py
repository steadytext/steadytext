# AIDEV-NOTE: Test suite for disk-backed frecency cache functionality
# Tests persistence, size limits, and eviction behavior
import os
import pickle
import tempfile
from pathlib import Path

import pytest

import sys
import os
# Disable model loading during cache tests
os.environ["STEADYTEXT_SKIP_MODEL_LOAD"] = "1"

from steadytext.disk_backed_frecency_cache import DiskBackedFrecencyCache


class TestDiskBackedFrecencyCache:
    """Test disk-backed frecency cache functionality."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_basic_persistence(self, temp_cache_dir):
        """Test that cache persists data to disk and loads on init."""
        # Create cache and add some data
        cache1 = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="test_cache",
            cache_dir=temp_cache_dir
        )
        
        cache1.set("key1", "value1")
        cache1.set("key2", "value2")
        cache1.set("key3", [1, 2, 3])  # Test different types
        
        # Verify cache file exists
        cache_file = temp_cache_dir / "test_cache.pkl"
        assert cache_file.exists()
        
        # Create new cache instance - should load from disk
        cache2 = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="test_cache",
            cache_dir=temp_cache_dir
        )
        
        # Verify data was loaded
        assert cache2.get("key1") == "value1"
        assert cache2.get("key2") == "value2"
        assert cache2.get("key3") == [1, 2, 3]
    
    def test_size_limit_eviction(self, temp_cache_dir):
        """Test that cache evicts entries when size limit is exceeded."""
        # Create cache with very small size limit (0.001 MB = 1KB)
        cache = DiskBackedFrecencyCache(
            capacity=100,
            cache_name="size_test",
            max_size_mb=0.001,  # 1KB limit
            cache_dir=temp_cache_dir
        )
        
        # Add data that will exceed 1KB when serialized
        large_value = "x" * 100  # 100 bytes per value
        for i in range(20):  # Should trigger eviction
            cache.set(f"key{i}", large_value)
        
        # Cache should have evicted some entries
        # Due to 20% eviction policy, should keep ~80% of entries
        count = sum(1 for i in range(20) if cache.get(f"key{i}") is not None)
        assert count < 20  # Some entries should be evicted
        assert count > 10  # But not all
    
    def test_clear_removes_file(self, temp_cache_dir):
        """Test that clear() removes the cache file."""
        cache = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="clear_test",
            cache_dir=temp_cache_dir
        )
        
        cache.set("key", "value")
        cache_file = temp_cache_dir / "clear_test.pkl"
        assert cache_file.exists()
        
        cache.clear()
        assert not cache_file.exists()
        assert cache.get("key") is None
    
    def test_corrupt_cache_recovery(self, temp_cache_dir):
        """Test that cache recovers from corrupted cache files."""
        cache_file = temp_cache_dir / "corrupt_test.pkl"
        
        # Write corrupted data
        with open(cache_file, "wb") as f:
            f.write(b"corrupted data that is not valid pickle")
        
        # Should not crash, just start fresh
        cache = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="corrupt_test",
            cache_dir=temp_cache_dir
        )
        
        # Should be empty after failed load
        assert cache.get("any_key") is None
        
        # Should still be functional
        cache.set("new_key", "new_value")
        assert cache.get("new_key") == "new_value"
    
    def test_frecency_behavior(self, temp_cache_dir):
        """Test that frecency algorithm is preserved in disk-backed version."""
        cache = DiskBackedFrecencyCache(
            capacity=3,
            cache_name="frecency_test",
            cache_dir=temp_cache_dir
        )
        
        # Fill cache
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        
        # Access 'a' multiple times to increase frequency
        for _ in range(3):
            cache.get("a")
        
        # Access 'c' once to update recency
        cache.get("c")
        
        # Add new item - should evict 'b' (lowest frecency)
        cache.set("d", 4)
        
        assert cache.get("a") == 1  # High frequency
        assert cache.get("b") is None  # Should be evicted
        assert cache.get("c") == 3  # Recent access
        assert cache.get("d") == 4  # Just added
    
    def test_thread_safety(self, temp_cache_dir):
        """Test thread-safe operations."""
        import threading
        
        cache = DiskBackedFrecencyCache(
            capacity=100,
            cache_name="thread_test",
            cache_dir=temp_cache_dir
        )
        
        def worker(thread_id):
            for i in range(10):
                cache.set(f"thread{thread_id}_key{i}", f"value{i}")
                cache.get(f"thread{thread_id}_key{i}")
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify all threads' data is present
        for thread_id in range(5):
            for i in range(10):
                key = f"thread{thread_id}_key{i}"
                assert cache.get(key) == f"value{i}"
    
    def test_sync_method(self, temp_cache_dir):
        """Test explicit sync() method."""
        cache = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="sync_test",
            cache_dir=temp_cache_dir
        )
        
        cache.set("key", "value")
        cache.sync()  # Explicit sync
        
        # Load cache file directly to verify
        cache_file = temp_cache_dir / "sync_test.pkl"
        with open(cache_file, "rb") as f:
            data = pickle.load(f)
        
        assert data["data"]["key"] == "value"
    
    def test_special_characters_in_keys(self, temp_cache_dir):
        """Test cache handles special characters in keys."""
        cache = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="special_test",
            cache_dir=temp_cache_dir
        )
        
        special_keys = [
            "key with spaces",
            "key\nwith\nnewlines",
            "key\twith\ttabs",
            "unicode_key_🔑",
            "key/with/slashes",
            "key\\with\\backslashes",
        ]
        
        for key in special_keys:
            cache.set(key, f"value_for_{key}")
        
        # Verify all keys work
        for key in special_keys:
            assert cache.get(key) == f"value_for_{key}"
        
        # Verify persistence
        cache2 = DiskBackedFrecencyCache(
            capacity=10,
            cache_name="special_test",
            cache_dir=temp_cache_dir
        )
        
        for key in special_keys:
            assert cache2.get(key) == f"value_for_{key}"