#pragma once
// Input order: thumb, index, middle, ring. Units: volts.
// Synthetic fixtures ONLY. Expected labels follow the dummy highest-voltage rule.
struct TestCase {
  float volts[4];
  char expected;
};
const TestCase testCases[] = {
  {{2.80f, 0.80f, 0.90f, 0.70f}, 'A'},
  {{0.80f, 2.80f, 0.90f, 0.70f}, 'B'},
  {{0.80f, 0.90f, 2.80f, 0.70f}, 'C'},
  {{0.80f, 0.90f, 0.70f, 2.80f}, 'D'},
  {{0.80f, 1.20f, 1.50f, 0.90f}, 'C'},
  {{1.40f, 0.70f, 1.10f, 1.60f}, 'D'},
  {{1.00f, 1.00f, 0.80f, 1.30f}, 'D'},
};
constexpr size_t testCount = sizeof(testCases) / sizeof(testCases[0]);
