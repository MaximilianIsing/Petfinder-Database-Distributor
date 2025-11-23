const fs = require('fs');
const path = require('path');

// Load GPT key from env or local file (same pattern as server.js)
let GPT_API_KEY = process.env.GPT_API_KEY || '';
if (!GPT_API_KEY) {
  try {
    GPT_API_KEY = fs.readFileSync(path.join(__dirname, 'gpt-key.txt'), 'utf8').trim();
  } catch (error) {
    // If there is no key, we will gracefully fall back to a neutral activities score.
    console.warn('rate-system: GPT API key not found; activities will be scored with a default value.');
  }
}

/**
 * Call GPT to rate a student's activities on a 1–10 scale.
 * Returns a number between 1 and 10 (or a neutral default of 5.5 on failure).
 *
 * @param {string} activitiesText - Multiline string describing activities.
 * @returns {Promise<number>}
 */
async function getActivitiesScore(activitiesText) {
  if (!activitiesText || !activitiesText.trim()) {
    return 5.5; // neutral if no activities provided
  }

  if (!GPT_API_KEY) {
    return 5.5;
  }

  const prompt = `
You are an experienced college admissions reader.
You will be given a student's extracurricular activities, formatted as one activity per line.
Rate the overall strength of the student's activities on a scale from 1 to 10, where:
- 1 means very weak activities,
- 5 means average/typical activities,
- 10 means exceptionally strong, highly impressive activities for competitive colleges.

Only respond with a single integer between 1 and 10, no explanation.

Student activities:
${activitiesText}
`.trim();

  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${GPT_API_KEY}`
      },
      body: JSON.stringify({
        model: 'gpt-4',
        messages: [
          { role: 'system', content: 'You are a strict but fair admissions reader. Answer with numbers only when asked for a score.' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.3,
        max_tokens: 10
      })
    });

    const data = await response.json();

    if (!response.ok) {
      console.error('rate-system: GPT API error:', data.error || data);
      return 5.5;
    }

    const raw = (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content || '').trim();
    const match = raw.match(/(\d+)/);
    const score = match ? parseInt(match[1], 10) : NaN;

    if (Number.isNaN(score)) {
      return 5.5;
    }

    return Math.min(10, Math.max(1, score));
  } catch (err) {
    console.error('rate-system: error calling GPT:', err);
    return 5.5;
  }
}

/**
 * Compute a relative score for a student based on academics and activities.
 * The score is on a 0–100 scale and is meant to be *relative*, not an official rating.
 *
 * @param {Object} student
 * @param {number|string} [student.gpa]            - GPA on a 0–4 (or 0–5) scale.
 * @param {boolean} [student.weighted=true]        - Whether GPA is weighted.
 * @param {number|string} [student.sat]            - SAT total (400–1600).
 * @param {number|string} [student.act]            - ACT composite (1–36).
 * @param {Array<{course:string, score:string|number}>} [student.apCourses] - AP courses with scores.
 * @param {string|Array<{hours:string, description:string}>} [student.activities] - Activities as string (legacy) or JSON array.
 * @returns {Promise<number>}                      - Promise resolving to a 0–100 score.
 */
async function rateStudent(student) {
  const {
    gpa,
    weighted = true,
    sat,
    act,
    apCourses = [],
    activities = ''
  } = student || {};

  // Convert activities array to string format for GPT
  let activitiesText = '';
  if (Array.isArray(activities)) {
    // Convert JSON array to multiline string format
    activitiesText = activities
      .filter(a => a && a.description)
      .map(a => {
        const hours = a.hours ? `${a.hours} hrs — ` : '';
        return hours + a.description;
      })
      .join('\n');
  } else if (typeof activities === 'string') {
    // Legacy string format - use as-is
    activitiesText = activities;
  }

  // --- Academic normalization helpers ---

  // GPA normalized to 0–1 (treat weighted GPAs as /5, unweighted as /4)
  const gpaNum = typeof gpa === 'string' ? parseFloat(gpa) : (gpa || 0);
  const gpaMax = weighted ? 5.0 : 4.0;
  const gpaNorm = gpaNum > 0 ? Math.min(1, gpaNum / gpaMax) : 0;

  // Test score normalized to 0–1, using whichever is stronger (SAT or ACT)
  const satNum = typeof sat === 'string' ? parseInt(sat, 10) : (sat || 0);
  const actNum = typeof act === 'string' ? parseInt(act, 10) : (act || 0);

  // If no test scores provided (all empty/0), treat as "Untaken" and assume average SAT score of 800
  const isUntaken = (satNum === 0 || sat === '' || sat === null || sat === undefined) && 
                     (actNum === 0 || act === '' || act === null || act === undefined);

  let satNorm = 0;
  if (isUntaken) {
    // Treat "Untaken" as SAT 800 (average score)
    satNorm = Math.min(1, (800 - 400) / (1600 - 400)); // (800 - 400) / 1200 = 0.333...
  } else if (satNum > 0) {
    satNorm = Math.min(1, (satNum - 400) / (1600 - 400)); // 400–1600
  }

  let actNorm = 0;
  if (!isUntaken && actNum > 0) {
    actNorm = Math.min(1, (actNum - 1) / (36 - 1)); // 1–36
  }

  const testNorm = Math.max(satNorm, actNorm);

  // AP rigor: combine count and average score into a 0–1 measure
  const validAps = (apCourses || []).filter(c => c && c.course);
  const apCount = validAps.length;
  let apAvgScore = 0;
  if (validAps.length > 0) {
    const total = validAps.reduce((sum, c) => {
      const s = typeof c.score === 'string' ? parseFloat(c.score) : (c.score || 0);
      return sum + (Number.isFinite(s) ? s : 0);
    }, 0);
    apAvgScore = total / validAps.length;
  }

  const apCountNorm = Math.min(1, apCount / 10);            // cap at 10 APs
  const apScoreNorm = Math.min(1, apAvgScore / 5);          // AP scores out of 5
  const apNorm = validAps.length > 0 ? (0.5 * apCountNorm + 0.5 * apScoreNorm) : 0;

  // Activities via GPT (0–1 after normalization)
  const activitiesScore10 = await getActivitiesScore(activitiesText);
  const activitiesNorm = activitiesScore10 / 10; // 1–10 → 0.1–1.0

  // --- Weighted combination into a 0–100 score ---
  // Weights should sum to 1.0
  const WEIGHTS = {
    gpa: 0.35,
    tests: 0.30,
    ap: 0.15,
    activities: 0.20
  };

  const composite =
    WEIGHTS.gpa * gpaNorm +
    WEIGHTS.tests * testNorm +
    WEIGHTS.ap * apNorm +
    WEIGHTS.activities * activitiesNorm;

  // Scale to 0–100 and round
  const score = Math.round(composite * 100);
  return score;
}

/**
 * Compute a relative score for a college based on its data.
 * The score is on a 0–100 scale and is meant to be *relative*, not an official rating.
 * Based on average/prestige indicators from the college's data.
 *
 * @param {Object} college
 * @param {number|string} [college.acceptance_rate]        - Acceptance rate (0-1, lower is more selective/prestigious).
 * @param {number|string} [college.sat_50th_percentile]    - Median SAT score (400-1600, higher is better).
 * @param {number|string} [college.act_50th_percentile]    - Median ACT score (1-36, higher is better).
 * @param {number|string} [college.graduation_rate]        - Graduation rate (0-1, higher is better).
 * @param {number|string} [college.retention_rate]         - Freshman retention rate (0-1, higher is better).
 * @param {number|string} [college.median_earnings_10_years] - Median earnings 10 years after graduation (higher is better).
 * @param {number|string} [college.enrollment]             - Total enrollment (can indicate prestige/size).
 * @param {number|string} [college.student_faculty_ratio]   - Student to faculty ratio (lower is better).
 * @returns {number}                                        - A 0–100 score.
 */
function rateCollege(college) {
  const {
    acceptance_rate,
    sat_50th_percentile,
    act_50th_percentile,
    graduation_rate,
    retention_rate,
    median_earnings_10_years,
    enrollment,
    student_faculty_ratio
  } = college || {};

  // Helper to parse numeric values
  const parseNum = (val) => {
    if (val === null || val === undefined || val === '') return null;
    const num = typeof val === 'string' ? parseFloat(val) : val;
    return Number.isFinite(num) ? num : null;
  };

  // --- Normalization helpers (all to 0–1 scale) ---

  // Acceptance rate: lower is better (more selective/prestigious)
  // Invert: 0.1 (10% acceptance) = 1.0, 0.9 (90% acceptance) = 0.0
  let acceptanceNorm = 0;
  const acceptanceRate = parseNum(acceptance_rate);
  if (acceptanceRate !== null && acceptanceRate >= 0 && acceptanceRate <= 1) {
    // Invert: highly selective (low acceptance) = high score
    acceptanceNorm = 1 - acceptanceRate; // 0.1 → 0.9, 0.9 → 0.1
    // Boost very selective schools (below 20% acceptance)
    if (acceptanceRate < 0.2) {
      acceptanceNorm = Math.min(1, acceptanceNorm * 1.2);
    }
  }

  // Test scores: higher is better, use whichever is available (SAT or ACT)
  const satScore = parseNum(sat_50th_percentile);
  const actScore = parseNum(act_50th_percentile);

  let satNorm = 0;
  if (satScore !== null && satScore >= 400 && satScore <= 1600) {
    satNorm = (satScore - 400) / (1600 - 400); // 400 → 0, 1600 → 1
  }

  let actNorm = 0;
  if (actScore !== null && actScore >= 1 && actScore <= 36) {
    actNorm = (actScore - 1) / (36 - 1); // 1 → 0, 36 → 1
  }

  // Use the higher normalized score (convert ACT to SAT equivalent if needed)
  // Rough conversion: ACT 36 ≈ SAT 1600, ACT 1 ≈ SAT 400
  const testNorm = Math.max(satNorm, actNorm);

  // Graduation rate: higher is better
  let graduationNorm = 0;
  const gradRate = parseNum(graduation_rate);
  if (gradRate !== null && gradRate >= 0 && gradRate <= 1) {
    graduationNorm = gradRate; // Already 0-1
  }

  // Retention rate: higher is better
  let retentionNorm = 0;
  const retRate = parseNum(retention_rate);
  if (retRate !== null && retRate >= 0 && retRate <= 1) {
    retentionNorm = retRate; // Already 0-1
  }

  // Median earnings: higher is better
  // Normalize assuming range of $30k-$150k (typical range)
  let earningsNorm = 0;
  const earnings = parseNum(median_earnings_10_years);
  if (earnings !== null && earnings > 0) {
    const minEarnings = 30000;
    const maxEarnings = 150000;
    earningsNorm = Math.min(1, Math.max(0, (earnings - minEarnings) / (maxEarnings - minEarnings)));
  }

  // Enrollment: moderate size can indicate prestige, but very large can be good too
  // Normalize assuming range of 500-50000
  let enrollmentNorm = 0;
  const enroll = parseNum(enrollment);
  if (enroll !== null && enroll > 0) {
    // Prefer moderate to large (5000-30000 range gets higher score)
    if (enroll >= 5000 && enroll <= 30000) {
      enrollmentNorm = 0.8 + (0.2 * (1 - Math.abs(enroll - 15000) / 15000)); // Peak at 15000
    } else if (enroll > 30000) {
      enrollmentNorm = 0.7; // Very large still good
    } else {
      enrollmentNorm = Math.min(0.6, enroll / 5000); // Smaller schools get lower score
    }
  }

  // Student-faculty ratio: lower is better (more personalized)
  // Normalize: 5:1 = 1.0, 25:1 = 0.0
  let ratioNorm = 0;
  const ratio = parseNum(student_faculty_ratio);
  if (ratio !== null && ratio > 0) {
    // Invert: lower ratio = higher score
    ratioNorm = Math.max(0, Math.min(1, 1 - (ratio - 5) / 20)); // 5 → 1.0, 25 → 0.0
  }

  // --- Weighted combination into a 0–100 score ---
  // Weights should sum to 1.0
  const WEIGHTS = {
    selectivity: 0.30,      // Acceptance rate (inverted)
    testScores: 0.25,       // SAT/ACT scores
    graduation: 0.15,       // Graduation rate
    retention: 0.10,        // Retention rate
    earnings: 0.10,         // Median earnings
    enrollment: 0.05,       // Enrollment size
    facultyRatio: 0.05      // Student-faculty ratio
  };

  const composite =
    WEIGHTS.selectivity * acceptanceNorm +
    WEIGHTS.testScores * testNorm +
    WEIGHTS.graduation * graduationNorm +
    WEIGHTS.retention * retentionNorm +
    WEIGHTS.earnings * earningsNorm +
    WEIGHTS.enrollment * enrollmentNorm +
    WEIGHTS.facultyRatio * ratioNorm;

  // Scale to 0–100 and round
  const score = Math.round(composite * 100);
  return score;
}

/**
 * Calculate admission odds based on student score, college score, and acceptance rate.
 * Uses the delta (difference) between scores and the college's acceptance rate to determine percentage chance.
 *
 * @param {number|string} studentScore - Student's rating score (0-100).
 * @param {number|string} collegeScore - College's rating score (0-100).
 * @param {number|string} [acceptanceRate] - College's acceptance rate (0-1, e.g., 0.15 for 15%).
 * @returns {number} - Admission odds as a percentage (0-100).
 */
function getAdmissionOdds(studentScore, collegeScore, acceptanceRate) {
  // Parse inputs
  const student = typeof studentScore === 'string' ? parseFloat(studentScore) : (studentScore || 0);
  const college = typeof collegeScore === 'string' ? parseFloat(collegeScore) : (collegeScore || 0);
  const acceptance = typeof acceptanceRate === 'string' ? parseFloat(acceptanceRate) : (acceptanceRate || null);

  // Ensure scores are in valid range
  const studentNorm = Math.max(0, Math.min(100, student));
  const collegeNorm = Math.max(0, Math.min(100, college));

  // Calculate delta (difference)
  const delta = studentNorm - collegeNorm;

  // Base odds when scores are equal - start from the college's acceptance rate if available
  // If no acceptance rate, default to 50%
  let baseOdds = 50;
  if (acceptance !== null && acceptance >= 0 && acceptance <= 1) {
    // Use acceptance rate as base, but adjust based on score delta
    // For example: 15% acceptance rate college = base odds of 15% when student matches college
    baseOdds = acceptance * 100;
  }

  // Calculate odds based on delta
  // Positive delta (student > college) = higher odds
  // Negative delta (student < college) = lower odds
  
  // Use a sigmoid-like curve for smooth transitions
  // Scale: each 10 points of delta = ~15% change in odds
  // Max delta impact: ±50 points = ±75% change (capped appropriately)
  
  const deltaMultiplier = 1.5; // Each point of delta = 1.5% change
  let odds = baseOdds + (delta * deltaMultiplier);

  // Apply sigmoid-like curve for more realistic distribution
  // This makes extreme differences less impactful
  const sigmoidFactor = 0.8; // Smoothing factor
  const normalizedDelta = delta / 50; // Normalize to -1 to 1 range
  const sigmoidDelta = (normalizedDelta / (1 + Math.abs(normalizedDelta) * sigmoidFactor)) * 50;
  odds = baseOdds + (sigmoidDelta * deltaMultiplier);

  // If acceptance rate is provided, use it as a constraint
  // The odds should not exceed the acceptance rate by too much, and should scale with it
  if (acceptance !== null && acceptance >= 0 && acceptance <= 1) {
    const acceptancePercent = acceptance * 100;
    
    // Scale the odds relative to the acceptance rate
    // If baseOdds was set from acceptance rate, we've already accounted for it
    // But we should ensure odds don't go too far above/below the acceptance rate based on delta alone
    
    // For highly selective schools (low acceptance), limit how high odds can go
    if (acceptancePercent < 20) {
      // Very selective: odds can go up to 2x the acceptance rate for strong students
      const maxOdds = Math.min(acceptancePercent * 2.5, 95);
      odds = Math.min(odds, maxOdds);
    } else if (acceptancePercent < 50) {
      // Moderately selective: odds can go up to 1.8x the acceptance rate
      const maxOdds = Math.min(acceptancePercent * 1.8, 95);
      odds = Math.min(odds, maxOdds);
    } else {
      // Less selective: odds can go higher, but still cap at reasonable level
      const maxOdds = Math.min(acceptancePercent * 1.5, 95);
      odds = Math.min(odds, maxOdds);
    }
    
    // Ensure odds don't go below a minimum based on acceptance rate
    // Even weak students have some chance at less selective schools
    if (acceptancePercent > 50) {
      const minOdds = Math.max(acceptancePercent * 0.3, 5);
      odds = Math.max(odds, minOdds);
    } else {
      const minOdds = Math.max(acceptancePercent * 0.2, 2);
      odds = Math.max(odds, minOdds);
    }
  }

  // Clamp to reasonable bounds (2% to 98%)
  odds = Math.max(2, Math.min(98, odds));

  // Round to nearest integer
  return Math.round(odds);
}

module.exports = {
  rateStudent,
  rateCollege,
  getAdmissionOdds
};


