(() => {
  const config = window.COST_ASSISTANT_CONFIG;
  const signInPanel = document.querySelector('#sign-in-panel');
  const assistantPanel = document.querySelector('#assistant-panel');
  const signInButton = document.querySelector('#sign-in');
  const signOutButton = document.querySelector('#sign-out');
  const form = document.querySelector('#question-form');
  const question = document.querySelector('#question');
  const answer = document.querySelector('#answer');
  const status = document.querySelector('#status');
  const askButton = document.querySelector('#ask');
  const sessionKey = 'costAssistantSessionId';
  const tokenKey = 'costAssistantIdToken';
  const verifierKey = 'costAssistantPkceVerifier';

  function base64Url(bytes) {
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function randomString() {
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return base64Url(bytes);
  }

  async function pkceChallenge(verifier) {
    return base64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  }

  function token() { return sessionStorage.getItem(tokenKey); }
  function sessionId() {
    let id = sessionStorage.getItem(sessionKey);
    if (!id) { id = crypto.randomUUID(); sessionStorage.setItem(sessionKey, id); }
    return id;
  }

  function showSignedIn() {
    signInPanel.hidden = true;
    assistantPanel.hidden = false;
    signOutButton.hidden = false;
  }

  function showSignedOut() {
    signInPanel.hidden = false;
    assistantPanel.hidden = true;
    signOutButton.hidden = true;
  }

  async function completeSignIn() {
    const code = new URLSearchParams(location.search).get('code');
    if (!code) return false;
    const verifier = sessionStorage.getItem(verifierKey);
    if (!verifier) throw new Error('The sign-in attempt expired. Please sign in again.');
    const body = new URLSearchParams({
      grant_type: 'authorization_code', code, client_id: config.clientId,
      redirect_uri: config.redirectUri, code_verifier: verifier,
    });
    const result = await fetch(`${config.cognitoDomain}/oauth2/token`, {
      method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body,
    });
    if (!result.ok) throw new Error('Sign-in could not be completed. Please try again.');
    const tokens = await result.json();
    sessionStorage.setItem(tokenKey, tokens.id_token);
    sessionStorage.removeItem(verifierKey);
    history.replaceState({}, document.title, location.pathname);
    return true;
  }

  async function beginSignIn() {
    const verifier = randomString();
    sessionStorage.setItem(verifierKey, verifier);
    const challenge = await pkceChallenge(verifier);
    const query = new URLSearchParams({
      client_id: config.clientId, response_type: 'code', scope: 'openid email',
      redirect_uri: config.redirectUri, code_challenge_method: 'S256', code_challenge: challenge,
    });
    location.assign(`${config.cognitoDomain}/login?${query}`);
  }

  function signOut() {
    sessionStorage.clear();
    const query = new URLSearchParams({ client_id: config.clientId, logout_uri: config.redirectUri });
    location.assign(`${config.cognitoDomain}/logout?${query}`);
  }

  async function ask(prompt) {
    answer.classList.remove('empty');
    answer.textContent = '';
    status.textContent = 'Checking your AWS cost data…';
    askButton.disabled = true;
    try {
      const result = await fetch(`${config.apiUrl}ask`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${token()}` },
        body: JSON.stringify({ prompt, sessionId: sessionId() }),
      });
      const data = await result.json();
      if (!result.ok) throw new Error(data.error || 'The request could not be completed.');
      answer.textContent = data.answer;
      status.textContent = '';
    } catch (error) {
      answer.textContent = error.message || 'The request could not be completed.';
      status.textContent = '';
    } finally {
      askButton.disabled = false;
    }
  }

  signInButton.addEventListener('click', beginSignIn);
  signOutButton.addEventListener('click', signOut);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const prompt = question.value.trim();
    if (prompt) ask(prompt);
  });
  document.querySelectorAll('[data-question]').forEach((button) => button.addEventListener('click', () => {
    question.value = button.dataset.question;
    ask(question.value);
  }));

  completeSignIn()
    .then(() => token() ? showSignedIn() : showSignedOut())
    .catch((error) => { showSignedOut(); signInPanel.querySelector('p').textContent = error.message; });
})();
