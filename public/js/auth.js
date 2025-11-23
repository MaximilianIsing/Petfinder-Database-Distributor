// Authentication utilities for Path Pal

/**
 * Hash a password using SHA-256
 * @param {string} password - Plain text password
 * @returns {Promise<string>} - Hashed password
 */
async function hashPassword(password) {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Generate a unique user ID
 * @returns {string} - User ID
 */
function generateUserId() {
  return 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

/**
 * Sign up a new user
 * @param {string} email - User email
 * @param {string} password - Plain text password
 * @returns {Promise<{success: boolean, userId?: string, error?: string}>}
 */
async function signUp(email, password) {
  try {
    if (!email || !password) {
      return { success: false, error: 'Email and password are required' };
    }

    if (!email.includes('@')) {
      return { success: false, error: 'Please enter a valid email address' };
    }

    if (password.length < 6) {
      return { success: false, error: 'Password must be at least 6 characters' };
    }

    const passwordHash = await hashPassword(password);
    
    const response = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        password_hash: passwordHash
      })
    });

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Sign up error:', error);
    return { success: false, error: 'An error occurred. Please try again.' };
  }
}

/**
 * Sign in an existing user
 * @param {string} email - User email
 * @param {string} password - Plain text password
 * @returns {Promise<{success: boolean, userId?: string, error?: string}>}
 */
async function signIn(email, password) {
  try {
    if (!email || !password) {
      return { success: false, error: 'Email and password are required' };
    }

    const passwordHash = await hashPassword(password);
    
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        password_hash: passwordHash
      })
    });

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Sign in error:', error);
    return { success: false, error: 'An error occurred. Please try again.' };
  }
}

/**
 * Continue as guest - generate a guest user ID
 * @returns {string} - Guest user ID
 */
function continueAsGuest() {
  const guestId = generateUserId();
  localStorage.setItem('user_id', guestId);
  localStorage.setItem('is_guest', 'true');
  return guestId;
}

/**
 * Set user session
 * @param {string} userId - User ID
 * @param {boolean} isGuest - Whether user is a guest
 */
function setUserSession(userId, isGuest = false) {
  localStorage.setItem('user_id', userId);
  localStorage.setItem('is_guest', isGuest ? 'true' : 'false');
}

/**
 * Get current user ID
 * @returns {string|null} - User ID or null
 */
function getCurrentUserId() {
  return localStorage.getItem('user_id');
}

/**
 * Check if current user is a guest
 * @returns {boolean}
 */
function isGuest() {
  return localStorage.getItem('is_guest') === 'true';
}

/**
 * Sign out current user
 */
function signOut() {
  localStorage.removeItem('user_id');
  localStorage.removeItem('is_guest');
}

