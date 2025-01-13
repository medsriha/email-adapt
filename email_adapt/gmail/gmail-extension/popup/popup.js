let currentToken = null;

document.addEventListener('DOMContentLoaded', function() {
    const connectGmailButton = document.getElementById('connect-gmail');
    const logoutButton = document.createElement('button');
    logoutButton.id = 'logout-gmail';
    logoutButton.innerHTML = 'Logout from Gmail';
    logoutButton.className = 'secondary-button';
    logoutButton.style.display = 'none'; // Initially hidden

    // Add logout button after the connect button
    connectGmailButton.parentNode.insertBefore(logoutButton, connectGmailButton.nextSibling);

    // Check connection status when popup opens
    chrome.storage.local.get(['isConnected', 'userEmail'], function(result) {
        console.log('Initial connection check:', result); // Debug log
        if (result.isConnected) {
            connectGmailButton.innerHTML = '✓ Connected!';
            connectGmailButton.disabled = true;
            connectGmailButton.style.display = 'none';
            logoutButton.style.display = 'block';
        }
    });

    const setButtonLoading = (isLoading) => {
        if (isLoading) {
            connectGmailButton.innerHTML = `
                <span class="spinner"></span>
                Connecting...`;
            connectGmailButton.disabled = true;
        } else {
            connectGmailButton.innerHTML = 'Connect your Gmail';
            connectGmailButton.disabled = false;
        }
    };
    
    connectGmailButton.addEventListener('click', async () => {
        try {
            setButtonLoading(true);
            
            // First, get the user's email from Chrome identity API
            chrome.identity.getAuthToken({ interactive: true }, async function(token) {
                if (chrome.runtime.lastError) {
                    console.error(chrome.runtime.lastError);
                    setButtonLoading(false);
                    connectGmailButton.textContent = 'Error connecting. Try again';
                    return;
                }

                // Store token securely instead of global variable
                await chrome.storage.local.set({ 'gmailToken': token });
                
                try {
                    // Get user info from Google
                    const response = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    const userInfo = await response.json();
                    
                    // Send email and token to your FastAPI backend first
                    const storeTokenResponseBackend = await fetch('http://localhost:8000/store-gmail-token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            email: userInfo.email,
                            token: token
                        })
                    });

                    if (!storeTokenResponseBackend.ok) {
                        const errorData = await storeTokenResponseBackend.json();
                        connectGmailButton.textContent = 'Error connecting. Try again';
                        throw new Error(`Failed to connect Gmail: ${errorData.detail || 'Unknown error'}`);
                    }
                    
                    // Store user email and connection status in chrome storage
                    await chrome.storage.local.set({ 
                        isConnected: true,
                        userEmail: userInfo.email 
                    });

                    // Only after successful backend response, update UI and redirect
                    connectGmailButton.innerHTML = '✓ Connected!';
                    connectGmailButton.disabled = true;
                    connectGmailButton.style.display = 'none';  // Hide connect button
                    logoutButton.style.display = 'block'; // Show logout button
                    
                    // Create new tab and switch to it immediately
                    chrome.tabs.create({ 
                        url: 'https://mail.google.com',
                        active: true  // Changed to true to switch to the tab immediately
                    }, async (tab) => {
                        // Wait for the tab to fully load
                        const waitForLoad = new Promise((resolve) => {
                            chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
                                if (tabId === tab.id && info.status === 'complete') {
                                    chrome.tabs.onUpdated.removeListener(listener);
                                    resolve();
                                }
                            });
                        });
                        
                        // Now proceed with handshake
                        try {
                            const handshakeResponse = await attemptHandshake();
                            console.log('Connection successful:', handshakeResponse);
                            
                            // After successful backend response
                            await chrome.storage.local.set({ 
                                isConnected: true, 
                                userEmail: userInfo.email 
                            });
                            console.log('Storage updated with connection status'); // Debug log
                            
                            // Verify the storage was set correctly
                            chrome.storage.local.get(['isConnected'], function(result) {
                                console.log('Storage after setting:', result); // Debug log
                            });
                        
                        } catch (error) {
                            console.error('Handshake failed:', error);
                            setButtonLoading(false);
                            connectGmailButton.textContent = 'Error connecting. Try again';
                        }

                        // Focus the tab after everything is done
                        setTimeout(() => {
                            chrome.tabs.update(tab.id, { active: true });
                        }, 1500);
                    });

                    // Function to handle handshake with retries
                    const attemptHandshake = async (retries = 3, delay = 1000) => {
                        for (let attempt = 1; attempt <= retries; attempt++) {
                            try {
                                const handshakeResponse = await fetch('http://localhost:8000/connect-gmail', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({
                                        email: userInfo.email,
                                        token: token
                                    })
                                });

                                if (!handshakeResponse.ok) {
                                    throw new Error(`Attempt ${attempt}: Failed to connect Gmail`);
                                }

                                return await handshakeResponse.json();
                            } catch (error) {
                                console.log(`Attempt ${attempt} failed:`, error);
                                if (attempt === retries) {
                                    throw new Error(`Failed after ${retries} attempts: ${error.message}`);
                                }
                                // Wait before next retry
                                await new Promise(resolve => setTimeout(resolve, delay));
                            }
                        }
                    };

                } catch (error) {
                    console.error('Error:', error);
                    setButtonLoading(false);
                    connectGmailButton.textContent = 'Error connecting. Try again';
                }
            });
        } catch (error) {
            console.error('Error:', error);
            setButtonLoading(false);
            connectGmailButton.textContent = 'Error connecting. Try again';
        }
    });

    // Logout handler
    logoutButton.addEventListener('click', async () => {
        try {
            const { userEmail, gmailToken } = await chrome.storage.local.get(['userEmail', 'gmailToken']);
            
            // Add check for userEmail
            if (!userEmail) {
                console.error('No user email found in storage');
                return;
            }

            // Clear stored connection state
            await chrome.storage.local.remove(['isConnected', 'userEmail', 'gmailToken']);

            // Revoke the token
            chrome.identity.removeCachedAuthToken({ token: gmailToken }, async () => {
                // Reset UI
                connectGmailButton.innerHTML = 'Connect your Gmail';
                connectGmailButton.disabled = false;
                connectGmailButton.style.display = 'block';
                logoutButton.style.display = 'none';
                
                // Update request to match backend expectations
                try {
                    const response = await fetch('http://localhost:8000/logout-gmail', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            email: userEmail
                        })
                    });

                    if (!response.ok) {
                        const errorData = await response.json();
                        console.error('Logout failed:', errorData);
                    }
                } catch (error) {
                    console.error('Failed to notify backend:', error);
                }
            });
        } catch (error) {
            console.error('Logout failed:', error);
        }
    });
});