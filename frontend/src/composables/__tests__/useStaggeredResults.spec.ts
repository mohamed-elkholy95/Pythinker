import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ref, nextTick } from 'vue';
import { useStaggeredResults } from '../useStaggeredResults';

describe('useStaggeredResults', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Progressive Reveal', () => {
    it('reveals results progressively with default delay (150ms)', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
        { id: 3, title: 'Result 3' },
      ]);

      const { visibleResults, isRevealing } = useStaggeredResults(sourceResults);

      // Initially revealing
      await nextTick();
      expect(isRevealing.value).toBe(true);
      expect(visibleResults.value).toHaveLength(1);
      expect(visibleResults.value[0].title).toBe('Result 1');

      // After 150ms - second result revealed
      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(2);
      expect(visibleResults.value[1].title).toBe('Result 2');

      // After another 150ms - third result revealed
      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(3);
      expect(visibleResults.value[2].title).toBe('Result 3');
      expect(isRevealing.value).toBe(false);
    });

    it('respects custom delay timing', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
      ]);

      const { visibleResults } = useStaggeredResults(sourceResults, {
        delayMs: 300,
      });

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // 150ms should not reveal second result (needs 300ms)
      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // After full 300ms - second result revealed
      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(2);
    });

    it('shows all results immediately when enabled=false', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
        { id: 3, title: 'Result 3' },
      ]);

      const { visibleResults, isRevealing } = useStaggeredResults(sourceResults, {
        enabled: false,
      });

      await nextTick();
      expect(visibleResults.value).toHaveLength(3);
      expect(isRevealing.value).toBe(false);
    });
  });

  describe('Source Changes', () => {
    it('resets and restarts reveal when source results change', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
      ]);

      const { visibleResults } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // Change source results
      sourceResults.value = [
        { id: 3, title: 'Result 3' },
        { id: 4, title: 'Result 4' },
        { id: 5, title: 'Result 5' },
      ];

      await nextTick();
      // Should reset and start revealing new results
      expect(visibleResults.value).toHaveLength(1);
      expect(visibleResults.value[0].title).toBe('Result 3');

      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(2);
      expect(visibleResults.value[1].title).toBe('Result 4');
    });

    it('clears visible results when source becomes empty', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
      ]);

      const { visibleResults } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // Clear source results
      sourceResults.value = [];

      await nextTick();
      expect(visibleResults.value).toHaveLength(0);
    });

    it('handles undefined source results gracefully', async () => {
      const sourceResults = ref(undefined);

      const { visibleResults, isRevealing } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toEqual([]);
      expect(isRevealing.value).toBe(false);
    });
  });

  describe('Cleanup', () => {
    it('clears pending timeouts when source changes mid-reveal', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
        { id: 3, title: 'Result 3' },
      ]);

      const { visibleResults } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // Change source mid-reveal (before all results revealed)
      sourceResults.value = [{ id: 4, title: 'Result 4' }];

      await nextTick();
      // Should stop previous reveal and start new one
      expect(visibleResults.value).toHaveLength(1);
      expect(visibleResults.value[0].title).toBe('Result 4');

      // Advance past old timing - should not reveal old results
      vi.advanceTimersByTime(500);
      await nextTick();
      expect(visibleResults.value).toHaveLength(1);
    });

    it('provides manual cleanup method', async () => {
      const sourceResults = ref([
        { id: 1, title: 'Result 1' },
        { id: 2, title: 'Result 2' },
      ]);

      const { visibleResults, cleanup } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);

      // Manual cleanup
      cleanup();

      expect(visibleResults.value).toEqual([]);

      // Advance timers should not reveal more results after cleanup
      vi.advanceTimersByTime(500);
      await nextTick();
      expect(visibleResults.value).toEqual([]);
    });
  });

  describe('Edge Cases', () => {
    it('handles single result array', async () => {
      const sourceResults = ref([{ id: 1, title: 'Result 1' }]);

      const { visibleResults, isRevealing } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);
      expect(isRevealing.value).toBe(false); // No more to reveal
    });

    it('handles large result sets efficiently', async () => {
      const largeResults = Array.from({ length: 100 }, (_, i) => ({
        id: i,
        title: `Result ${i}`,
      }));

      const sourceResults = ref(largeResults);

      const { visibleResults, isRevealing } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value).toHaveLength(1);
      expect(isRevealing.value).toBe(true);

      // Reveal 10 results (10 * 150ms = 1500ms)
      vi.advanceTimersByTime(1500);
      await nextTick();
      expect(visibleResults.value).toHaveLength(11); // First + 10 more

      // Reveal all remaining results
      vi.advanceTimersByTime(100 * 150);
      await nextTick();
      expect(visibleResults.value).toHaveLength(100);
      expect(isRevealing.value).toBe(false);
    });

    it('maintains result object data correctly', async () => {
      const result1 = { id: 1, title: 'Result 1' };
      const result2 = { id: 2, title: 'Result 2' };
      const sourceResults = ref([result1, result2]);

      const { visibleResults } = useStaggeredResults(sourceResults);

      await nextTick();
      expect(visibleResults.value[0]).toStrictEqual(result1); // Same data

      vi.advanceTimersByTime(150);
      await nextTick();
      expect(visibleResults.value[1]).toStrictEqual(result2); // Same data
    });
  });

  describe('Reactivity', () => {
    it('maintains reactivity when results are updated in place', async () => {
      const result1 = { id: 1, title: 'Result 1' };
      const sourceResults = ref([result1]);

      const { visibleResults } = useStaggeredResults(sourceResults, {
        enabled: false, // Instant reveal for this test
      });

      await nextTick();
      expect(visibleResults.value[0].title).toBe('Result 1');

      // Mutate the source result
      result1.title = 'Updated Result 1';

      await nextTick();
      // Visible result should reflect the mutation (same reference)
      expect(visibleResults.value[0].title).toBe('Updated Result 1');
    });
  });
});
