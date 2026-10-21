#pragma once
// Generated with model_data.h; replace both headers together.
// Model SHA256: f342f75676d2af61d487ec89a2a8a4655ab2243abc00709a7a243b5e8882ea97
// Input order: thumb, index, middle, ring, pinky. Preprocessing is outside the model.
// normalized[i] = (raw[i] - kInputOffset[i]) * kInputScale[i]
inline constexpr float kInputOffset[5] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
inline constexpr float kInputScale[5] = {
    1.0f / 4095.0f, 1.0f / 4095.0f, 1.0f / 4095.0f,
    1.0f / 4095.0f, 1.0f / 4095.0f
};
