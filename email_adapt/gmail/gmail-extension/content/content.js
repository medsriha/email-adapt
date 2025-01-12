// Add this at the top of your content.js
const DEBUG = true;

// Helpful function for debugging
function debugLog(message, data) {
  if (DEBUG) {
    console.log(
      `%c[Gmail Extension] ${message}`,
      'background: #f0f0f0; color: #333; padding: 2px 4px; border-radius: 2px;',
      data
    );
  }
}

// Function to extract email thread content
function extractEmailThread() {
  const threadContainer = document.querySelector('div[role="main"]');
  const emails = threadContainer.querySelectorAll('.h7');
  
  const threadData = Array.from(emails).map(email => ({
    sender: email.querySelector('.gD').getAttribute('email'),
    content: email.querySelector('.a3s').innerText,
    timestamp: email.querySelector('.g3').getAttribute('title')
  }));

  return threadData;
}

// Function to send thread data to backend
async function sendThreadToBackend(threadData) {
  try {
    const response = await fetch('YOUR_BACKEND_URL/analyze-thread', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ threadData })
    });

    const analysis = await response.json();
    // Handle the backend response here
    console.log('Thread analysis:', analysis);
    
    // You can show the analysis results in a custom UI element
    showAnalysisResults(analysis);
  } catch (error) {
    console.error('Error sending thread to backend:', error);
  }
}

// Function to show analysis results
function showAnalysisResults(analysis) {
  // Create or update UI element to show results
  const resultsDiv = document.createElement('div');
  resultsDiv.innerHTML = `
    <div style="position: fixed; right: 20px; top: 20px; background: white; padding: 15px; border: 1px solid #ccc; border-radius: 5px;">
      <h3>Analysis Results</h3>
      <pre>${JSON.stringify(analysis, null, 2)}</pre>
    </div>
  `;
  document.body.appendChild(resultsDiv);
}

// Observer to detect when email thread is loaded
const observer = new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    if (mutation.addedNodes.length) {
      const threadContainer = document.querySelector('div[role="main"]');
      if (threadContainer) {
        const threadData = extractEmailThread();
        if (threadData.length > 0) {
          sendThreadToBackend(threadData);
        }
      }
    }
  }
});

// Start observing DOM changes
observer.observe(document.body, {
  childList: true,
  subtree: true
}); 