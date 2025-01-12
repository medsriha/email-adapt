const API_BASE_URL = 'YOUR_BACKEND_URL';

export const verifyEmail = async (email) => {
  try {
    const response = await fetch(`${API_BASE_URL}/verify-email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email })
    });
    return await response.json();
  } catch (error) {
    console.error('Error verifying email:', error);
    throw error;
  }
};

export const analyzeThread = async (threadData) => {
  try {
    const response = await fetch(`${API_BASE_URL}/analyze-thread`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ threadData })
    });
    return await response.json();
  } catch (error) {
    console.error('Error analyzing thread:', error);
    throw error;
  }
};