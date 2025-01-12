const DEBUG = true;

if (DEBUG) console.log('Debug info:', someVariable); 

document.addEventListener('DOMContentLoaded', function() {
  const emailForm = document.getElementById('emailForm');
  const statusMessage = document.getElementById('statusMessage');
  const submitButton = document.getElementById('submitEmail');
  const emailInput = document.getElementById('userEmail');

  // Check if email is already verified
  chrome.storage.local.get(['verifiedEmail'], function(result) {
    if (result.verifiedEmail) {
      emailForm.classList.add('hidden');
      statusMessage.classList.remove('hidden');
    }
  });

  submitButton.addEventListener('click', async function() {
    const email = emailInput.value;
    
    try {
      const response = await fetch('YOUR_BACKEND_URL/verify-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email })
      });

      const data = await response.json();
      
      if (data.verified) {
        chrome.storage.local.set({ verifiedEmail: email });
        emailForm.classList.add('hidden');
        statusMessage.classList.remove('hidden');
      }
    } catch (error) {
      console.error('Error verifying email:', error);
    }
  });
}); 