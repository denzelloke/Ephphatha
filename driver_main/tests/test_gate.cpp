#include <cassert>
#include "gesture_gate.h"
int main() {
    GestureGate gate(0.8f, 3, 1500);
    assert(!gate.update(1, .9f, false, 0));
    assert(!gate.update(1, .9f, false, 100));
    assert(gate.update(1, .9f, false, 200));
    gate.mark_spoken(1, 200);
    assert(!gate.update(1, .9f, false, 2000)); // held gesture
    assert(!gate.update(1, .2f, false, 2100)); // uncertainty does not rearm
    for (int i = 0; i < 4; ++i) assert(!gate.update(1, .9f, false, 2200 + i*100));
    for (int i = 0; i < 3; ++i) assert(!gate.update(0, .9f, true, 3000 + i*100));
    assert(!gate.update(1, .9f, false, 3300));
    assert(!gate.update(1, .9f, false, 3400));
    assert(gate.update(1, .9f, false, 3500)); // neutral -> same gesture
    gate.mark_spoken(1, 3500);
    assert(!gate.update(2, .9f, false, 3600));
    assert(!gate.update(2, .9f, false, 3700));
    assert(!gate.update(2, .9f, false, 3800)); // cooldown
    assert(gate.update(2, .9f, false, 5000)); // distinct stable gesture
    gate.invalidate();
    assert(!gate.update(2, .9f, false, 5100));
    gate.reset();
    assert(!gate.update(3, .9f, false, 0));
    assert(!gate.update(3, .9f, false, 100));
    assert(gate.update(3, .9f, false, 200));
}
