#include "model_data.h"
#include "model_settings.h"

static_assert(GLOVE_HAS_MODEL == 1);
static_assert(kClassCount == 27);
static_assert(sizeof(kInputOffset) / sizeof(float) == 5);
static_assert(sizeof(kInputScale) / sizeof(float) == 5);
static_assert(sizeof(kLabels) / sizeof(kLabels[0]) == kClassCount);
static_assert(sizeof(kTracks) / sizeof(kTracks[0]) == kClassCount);
static_assert(kTracks[0] == 0 && kTracks[1] == 1 && kTracks[26] == 26);
static_assert(kLabels[0][0] == '!' && kLabels[1][0] == 'a' && kLabels[26][0] == 'z');
static_assert(g_model_data[4] == 'T' && g_model_data[5] == 'F');
static_assert(g_model_data[6] == 'L' && g_model_data[7] == '3');
static_assert(kInputScale[0] == 1.0f / 4095.0f);

int main() { return g_model_data_len > 12 ? 0 : 1; }
