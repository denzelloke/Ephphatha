#pragma once
#include <cstdint>

// Independent of ESP-IDF, so the decision logic can be tested on a PC.
class GestureGate {
public:
    GestureGate(float threshold, int stable_count, int cooldown_ms)
        : threshold_(threshold), stable_count_(stable_count), cooldown_ms_(cooldown_ms) {}
    void reset() {
        candidate_ = -1; count_ = 0; last_spoken_ = -1; last_time_ = -1;
    }
    void invalidate() { candidate_ = -1; count_ = 0; }
    // neutral is a confident prediction of label "!", not low confidence.
    bool update(int index, float confidence, bool neutral, int64_t now_ms) {
        if (index < 0 || !(confidence >= threshold_)) { invalidate(); return false; }
        if (candidate_ != index) { candidate_ = index; count_ = 1; }
        else if (count_ < stable_count_) ++count_;
        if (count_ < stable_count_) return false;
        if (neutral) { last_spoken_ = -1; return false; }
        if (index == last_spoken_) return false;
        if (last_time_ >= 0 && now_ms - last_time_ < cooldown_ms_) return false;
        return true;
    }
    // Commit only after a successful UART transmission.
    void mark_spoken(int index, int64_t now_ms) { last_spoken_ = index; last_time_ = now_ms; }
private:
    float threshold_;
    int stable_count_, cooldown_ms_;
    int candidate_ = -1, count_ = 0, last_spoken_ = -1;
    int64_t last_time_ = -1;
};
