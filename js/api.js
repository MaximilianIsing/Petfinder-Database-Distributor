// API utility functions

const API_BASE = '';

// GPT Chat API
async function sendChatMessage(message, context = []) {
  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ message, context })
    });
    
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    
    return await response.json();
  } catch (error) {
    console.error('Chat API error:', error);
    throw error;
  }
}

// Local storage utilities
const Storage = {
  get(key, defaultValue = null) {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue;
    } catch (error) {
      console.error('Storage get error:', error);
      return defaultValue;
    }
  },
  
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error('Storage set error:', error);
    }
  },
  
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.error('Storage remove error:', error);
    }
  }
};

// User profile data management
const UserProfile = {
  get() {
    return Storage.get('userProfile', {
      name: '',
      grade: '',
      gpa: '',
      weighted: true,
      sat: '',
      act: '',
      psat: '',
      majors: [],
      activities: [],
      interests: [],
      careerGoals: ''
    });
  },
  
  save(profile) {
    Storage.set('userProfile', profile);
  },
  
  update(updates) {
    const profile = this.get();
    const updated = { ...profile, ...updates };
    this.save(updated);
    return updated;
  }
};

// Saved colleges management
const SavedColleges = {
  get() {
    return Storage.get('savedColleges', []);
  },
  
  add(college) {
    const colleges = this.get();
    if (!colleges.find(c => c.id === college.id)) {
      colleges.push(college);
      Storage.set('savedColleges', colleges);
    }
  },
  
  remove(collegeId) {
    const colleges = this.get().filter(c => c.id !== collegeId);
    Storage.set('savedColleges', colleges);
  },
  
  isSaved(collegeId) {
    return this.get().some(c => c.id === collegeId);
  }
};

// Mock college data
const Colleges = [
  { id: 1, name: 'Stanford University', location: 'California', size: 'Medium', type: 'Private', acceptanceRate: 0.04, category: 'reach' },
  { id: 2, name: 'MIT', location: 'Massachusetts', size: 'Medium', type: 'Private', acceptanceRate: 0.07, category: 'reach' },
  { id: 3, name: 'University of California Berkeley', location: 'California', size: 'Large', type: 'Public', acceptanceRate: 0.17, category: 'reach' },
  { id: 4, name: 'UCLA', location: 'California', size: 'Large', type: 'Public', acceptanceRate: 0.14, category: 'reach' },
  { id: 5, name: 'University of Michigan', location: 'Michigan', size: 'Large', type: 'Public', acceptanceRate: 0.23, category: 'target' },
  { id: 6, name: 'University of Texas Austin', location: 'Texas', size: 'Large', type: 'Public', acceptanceRate: 0.31, category: 'target' },
  { id: 7, name: 'Penn State University', location: 'Pennsylvania', size: 'Large', type: 'Public', acceptanceRate: 0.54, category: 'safety' },
  { id: 8, name: 'Arizona State University', location: 'Arizona', size: 'Large', type: 'Public', acceptanceRate: 0.88, category: 'safety' }
];

// Calculate admissions odds (mock calculation)
function calculateAdmissionOdds(profile, college) {
  // Simplified calculation - in real app, this would use ML models
  let score = 0.5; // Base score
  
  if (profile.gpa) {
    const gpa = parseFloat(profile.gpa);
    if (gpa >= 4.0) score += 0.2;
    else if (gpa >= 3.7) score += 0.15;
    else if (gpa >= 3.5) score += 0.1;
    else if (gpa >= 3.0) score += 0.05;
  }
  
  if (profile.sat) {
    const sat = parseInt(profile.sat);
    if (sat >= 1500) score += 0.2;
    else if (sat >= 1400) score += 0.15;
    else if (sat >= 1300) score += 0.1;
    else if (sat >= 1200) score += 0.05;
  }
  
  if (profile.act) {
    const act = parseInt(profile.act);
    if (act >= 34) score += 0.2;
    else if (act >= 31) score += 0.15;
    else if (act >= 28) score += 0.1;
    else if (act >= 25) score += 0.05;
  }
  
  // Adjust based on college acceptance rate
  score = score * (1 - college.acceptanceRate * 0.7);
  
  return Math.min(Math.max(score * 100, 5), 95); // Clamp between 5% and 95%
}

function categorizeSchool(odds) {
  if (odds >= 70) return { category: 'safety', label: 'Safety' };
  if (odds >= 40) return { category: 'target', label: 'Target' };
  return { category: 'reach', label: 'Reach' };
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { sendChatMessage, Storage, UserProfile, SavedColleges, Colleges, calculateAdmissionOdds, categorizeSchool };
}

