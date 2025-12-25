/**
 * Inactivity Warning System
 * Shows a warning 2 minutes before session expires
 * Auto-logs out user after 30 minutes of inactivity
 * Also pings Portal keepalive to prevent cross-system session expiry
 */

(function() {
    const SESSION_TIMEOUT_MS = 30 * 60 * 1000;  // 30 minutes
    const WARNING_BEFORE_MS = 2 * 60 * 1000;    // Show warning 2 min before
    const WARNING_TIME_MS = SESSION_TIMEOUT_MS - WARNING_BEFORE_MS;
    const THROTTLE_MS = 1000;  // Throttle activity detection to 1 second
    const KEEPALIVE_INTERVAL_MS = 5 * 60 * 1000;  // Ping Portal every 5 minutes

    let activityTimer = null;
    let warningTimer = null;
    let warningModal = null;
    let countdownInterval = null;
    let keepaliveInterval = null;
    let lastActivityTime = Date.now();

    function createWarningModal() {
        const modalHtml = '<div class="modal fade" id="inactivityWarningModal" data-bs-backdrop="static" data-bs-keyboard="false" tabindex="-1">' +
            '<div class="modal-dialog modal-dialog-centered">' +
            '<div class="modal-content" style="background-color: #1c2128; border: 1px solid #ffc107;">' +
            '<div class="modal-header" style="border-bottom: 1px solid #ffc107;">' +
            '<h5 class="modal-title" style="color: #ffc107;">' +
            '<i class="bi bi-exclamation-triangle-fill me-2"></i>Session Expiring Soon</h5></div>' +
            '<div class="modal-body" style="color: #c9d1d9;">' +
            '<p>Your session will expire due to inactivity in:</p>' +
            '<h2 class="text-center text-warning mb-3" id="countdownDisplay">2:00</h2>' +
            '<p class="mb-0">Click "Stay Logged In" to continue your session.</p></div>' +
            '<div class="modal-footer" style="border-top: 1px solid #30363d;">' +
            '<button type="button" class="btn btn-warning" id="stayLoggedInBtn">' +
            '<i class="bi bi-check-circle me-1"></i>Stay Logged In</button></div></div></div></div>';

        if (!document.getElementById('inactivityWarningModal')) {
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        }

        warningModal = new bootstrap.Modal(document.getElementById('inactivityWarningModal'));

        document.getElementById('stayLoggedInBtn').addEventListener('click', function() {
            resetActivity(true);  // Force reset
            pingPortalKeepalive();  // Also refresh Portal session
            warningModal.hide();
        });
    }

    function showWarning() {
        if (!warningModal) {
            createWarningModal();
        }
        warningModal.show();
        startCountdown();
    }

    function startCountdown() {
        let secondsLeft = WARNING_BEFORE_MS / 1000;
        const display = document.getElementById('countdownDisplay');

        countdownInterval = setInterval(function() {
            secondsLeft--;
            const minutes = Math.floor(secondsLeft / 60);
            const seconds = secondsLeft % 60;
            const secStr = seconds < 10 ? '0' + seconds : seconds;
            display.textContent = minutes + ':' + secStr;

            if (secondsLeft <= 0) {
                clearInterval(countdownInterval);
                logout();
            }
        }, 1000);
    }

    function logout() {
        clearTimeout(activityTimer);
        clearTimeout(warningTimer);
        clearInterval(countdownInterval);
        clearInterval(keepaliveInterval);
        localStorage.clear();
        sessionStorage.clear();
        // Redirect to portal login with reason
        window.location.href = '/portal/login?reason=inactivity';
    }

    /**
     * Ping Portal keepalive endpoint to refresh the Portal session cookie.
     * This prevents the Portal session from expiring while user is active
     * in a sub-system, which would cause logout when navigating to another system.
     */
    function pingPortalKeepalive() {
        fetch('/portal/api/keepalive', {
            method: 'GET',
            credentials: 'include'  // Include cookies for Portal auth
        })
        .then(function(response) {
            if (response.status === 401) {
                // Portal session already expired - redirect to login
                console.log('Portal session expired, redirecting to login');
                logout();
            } else if (response.ok) {
                console.log('Portal session keepalive successful');
            }
        })
        .catch(function(error) {
            console.log('Portal keepalive ping failed (may be offline):', error);
        });
    }

    function resetActivity(force) {
        // Throttle activity detection unless forced
        const now = Date.now();
        if (!force && (now - lastActivityTime) < THROTTLE_MS) {
            return;
        }
        lastActivityTime = now;

        clearTimeout(activityTimer);
        clearTimeout(warningTimer);
        clearInterval(countdownInterval);

        if (warningModal && document.getElementById('inactivityWarningModal')) {
            const modalEl = document.getElementById('inactivityWarningModal');
            if (modalEl.classList.contains('show')) {
                warningModal.hide();
            }
        }

        warningTimer = setTimeout(showWarning, WARNING_TIME_MS);
        activityTimer = setTimeout(logout, SESSION_TIMEOUT_MS);
    }

    function setupActivityTracking() {
        // Only track INTENTIONAL user activity (not passive like mousemove)
        // mousemove was removed because it fires constantly with any mouse movement
        // preventing proper inactivity detection
        const events = ['mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
        events.forEach(function(event) {
            document.addEventListener(event, function() { resetActivity(false); }, { passive: true });
        });
    }

    function startKeepalive() {
        // Ping Portal immediately on load to refresh session
        pingPortalKeepalive();

        // Then ping every 5 minutes to keep Portal session alive
        keepaliveInterval = setInterval(pingPortalKeepalive, KEEPALIVE_INTERVAL_MS);
    }

    // Expose for external use (e.g., "Stay Logged In" buttons)
    window.resetInactivityTimer = function() { resetActivity(true); };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setupActivityTracking();
            resetActivity(true);
            startKeepalive();
        });
    } else {
        setupActivityTracking();
        resetActivity(true);
        startKeepalive();
    }
})();
