#include "thermal_nexus_model.h"

static const int CHILDREN_LEFT[] = {1, 2, 3, 4, 5, -1, -1, -1, 9, 10, -1, -1, 13, -1, -1, 16, 17, -1, -1, 20, -1, 22, -1, -1, 25, 26, 27, -1, -1, -1, -1};
static const int CHILDREN_RIGHT[] = {24, 15, 8, 7, 6, -1, -1, -1, 12, 11, -1, -1, 14, -1, -1, 19, 18, -1, -1, 21, -1, 23, -1, -1, 30, 29, 28, -1, -1, -1, -1};
static const int FEATURE_INDEX[] = {6, 33, 28, 21, 26, -2, -2, -2, 27, 28, -2, -2, 29, -2, -2, 20, 6, -2, -2, 29, -2, 29, -2, -2, 7, 17, 29, -2, -2, -2, -2};
static const float THRESHOLDS[] = {5.70149994f, 0.000582635956f, 3.82314992f, 4.13179994f, 3.99940097f, -2f, -2f, -2f, 0.860742599f, 3.88824999f, -2f, -2f, 9.67055035f, -2f, -2f, 4.35684991f, 3.05335009f, -2f, -2f, 9.65164995f, -2f, 9.68085003f, -2f, -2f, 0.248199999f, -0.00199175003f, 9.68085003f, -2f, -2f, -2f, -2f};
static const float LEAF_PROBA[][THERMAL_NEXUS_CLASS_COUNT] = {
    {0.409207161f, 0.462574595f, 0.128218244f},
    {0.0846403461f, 0.720930233f, 0.194429421f},
    {0.0889039701f, 0.835086529f, 0.0760095012f},
    {0.509615385f, 0.134615385f, 0.355769231f},
    {0.166666667f, 0.233333333f, 0.6f},
    {0.25f, 0f, 0.75f},
    {0f, 0.7f, 0.3f},
    {0.977272727f, 0f, 0.0227272727f},
    {0.0735138938f, 0.860710517f, 0.0657755892f},
    {0.0365709792f, 0.900904444f, 0.0625245773f},
    {0.12254902f, 0.720588235f, 0.156862745f},
    {0.00932159503f, 0.958052822f, 0.0326255826f},
    {0.386666667f, 0.52f, 0.0933333333f},
    {0.627027027f, 0.248648649f, 0.124324324f},
    {0f, 0.956521739f, 0.0434782609f},
    {0.0679094541f, 0.272969374f, 0.659121172f},
    {0.239130435f, 0.755434783f, 0.00543478261f},
    {0f, 1f, 0f},
    {0.977777778f, 0f, 0.0222222222f},
    {0.012345679f, 0.116402116f, 0.871252205f},
    {0.0141414141f, 0.0161616162f, 0.96969697f},
    {0f, 0.805555556f, 0.194444444f},
    {0f, 0.5f, 0.5f},
    {0f, 1f, 0f},
    {0.963082603f, 0.0216889709f, 0.0152284264f},
    {0.675925926f, 0.199074074f, 0.125f},
    {0.0303030303f, 0.621212121f, 0.348484848f},
    {0f, 0.206896552f, 0.793103448f},
    {0.0540540541f, 0.945945946f, 0f},
    {0.96f, 0.0133333333f, 0.0266666667f},
    {0.994874423f, 0.00205023065f, 0.00307534598f}
};

static int thermal_nexus_leaf(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {
    int node = 0;
    while (CHILDREN_LEFT[node] != -1) {
        int feature = FEATURE_INDEX[node];
        if (features[feature] <= THRESHOLDS[node]) {
            node = CHILDREN_LEFT[node];
        } else {
            node = CHILDREN_RIGHT[node];
        }
    }
    return node;
}

void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]) {
    int leaf = thermal_nexus_leaf(features);
    for (int i = 0; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {
        probabilities[i] = LEAF_PROBA[leaf][i];
    }
}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {
    float probabilities[THERMAL_NEXUS_CLASS_COUNT];
    thermal_nexus_predict_proba(features, probabilities);
    int best = 0;
    for (int i = 1; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {
        if (probabilities[i] > probabilities[best]) {
            best = i;
        }
    }
    return best;
}
