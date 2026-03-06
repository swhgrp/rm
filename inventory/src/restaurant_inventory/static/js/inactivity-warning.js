/**
 * Inactivity Warning System
 * Shows a warning 2 minutes before session expires
 * Auto-logs out user after 30 minutes of inactivity
 * Pings Portal and local system keepalive endpoints to extend sessions on activity
 */

(function() {
    const SESSION_TIMEOUT_MS = 30 * 60 * 1000;  // 30 minutes
    const WARNING_BEFORE_MS = 2 * 60 * 1000;    // Show warning 2 min before
    const WARNING_TIME_MS = SESSION_TIMEOUT_MS - WARNING_BEFORE_MS;
    const THROTTLE_MS = 1000;  // Throttle activity detection to 1 second
    const KEEPALIVE_INTERVAL_MS = 5 * 60 * 1000;  // Ping keepalive every 5 minutes

    let activityTimer = null;
    let warningTimer = null;
    let warningModal = null;
    let countdownInterval = null;
    let keepaliveInterval = null;
    let lastActivityTime = Date.now();

    /**
     * Detect the current system's keepalive URL based on the page path.
     * Maps path prefixes to their API keepalive endpoints.
     */
    function getLocalKeepaliveUrl() {
        var path = window.location.pathname;
        if (path.indexOf('/events') === 0) return '/events/api/auth/keepalive';
        if (path.indexOf('/accounting') === 0) return '/accounting/api/auth/keepalive';
        if (path.indexOf('/hr') === 0) return '/hr/api/auth/keepalive';
        if (path.indexOf('/files') === 0) return '/files/api/auth/keepalive';
        if (path.indexOf('/inventory') === 0) return '/inventory/api/auth/keepalive';
        if (path.indexOf('/hub') === 0) return '/hub/api/auth/keepalive';
        // Portal or unknown - only Portal keepalive needed
        return null;
    }

    function createWarningModal() {
        var modalHtml = '<div class="modal fade" id="inactivityWarningModal" data-bs-backdrop="static" data-bs-keyboard="false" tabindex="-1">' +
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
            pingKeepalive();  // Refresh both Portal and local sessions
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
        var secondsLeft = WARNING_BEFORE_MS / 1000;
        var display = document.getElementById('countdownDisplay');

        countdownInterval = setInterval(function() {
            secondsLeft--;
            var minutes = Math.floor(secondsLeft / 60);
            var seconds = secondsLeft % 60;
            var secStr = seconds < 10 ? '0' + seconds : seconds;
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
     * Ping Portal keepalive to refresh the Portal session cookie.
     * Also pings the local system's keepalive to extend the backend session.
     */
    function pingKeepalive() {
        // Ping Portal keepalive
        fetch('/portal/api/keepalive', {
            method: 'GET',
            credentials: 'include'
        })
        .then(function(response) {
            if (response.status === 401) {
                console.log('Portal session expired, redirecting to login');
                logout();
            }
        })
        .catch(function(error) {
            console.log('Portal keepalive ping failed:', error);
        });

        // Ping local system keepalive to extend the backend session
        var localUrl = getLocalKeepaliveUrl();
        if (localUrl) {
            var headers = {};
            var token = localStorage.getItem('access_token');
            if (token) {
                headers['Authorization'] = 'Bearer ' + token;
            }
            fetch(localUrl, {
                method: 'GET',
                credentials: 'include',
                headers: headers
            })
            .then(function(response) {
                if (response.status === 401) {
                    console.log('Local session expired, redirecting to login');
                    logout();
                } else if (response.ok) {
                    response.json().then(function(data) {
                        if (data.access_token) {
                            localStorage.setItem('access_token', data.access_token);
                        }
                    });
                }
            })
            .catch(function(error) {
                console.log('Local keepalive ping failed:', error);
            });
        }
    }

    function resetActivity(force) {
        // Throttle activity detection unless forced
        var now = Date.now();
        if (!force && (now - lastActivityTime) < THROTTLE_MS) {
            return;
        }
        lastActivityTime = now;

        clearTimeout(activityTimer);
        clearTimeout(warningTimer);
        clearInterval(countdownInterval);

        if (warningModal && document.getElementById('inactivityWarningModal')) {
            var modalEl = document.getElementById('inactivityWarningModal');
            if (modalEl.classList.contains('show')) {
                warningModal.hide();
            }
        }

        warningTimer = setTimeout(showWarning, WARNING_TIME_MS);
        activityTimer = setTimeout(logout, SESSION_TIMEOUT_MS);
    }

    function setupActivityTracking() {
        // Only track INTENTIONAL user activity (not passive like mousemove)
        var events = ['mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
        events.forEach(function(event) {
            document.addEventListener(event, function() { resetActivity(false); }, { passive: true });
        });
    }

    function startKeepalive() {
        // Ping keepalive immediately on load to refresh sessions
        pingKeepalive();

        // Then ping every 5 minutes to keep sessions alive while user is active
        keepaliveInterval = setInterval(pingKeepalive, KEEPALIVE_INTERVAL_MS);
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
