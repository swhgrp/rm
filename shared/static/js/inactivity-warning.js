/**
 * Inactivity Warning System
 * Shows a warning 2 minutes before session expires
 */

(function() {
    const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
    const WARNING_BEFORE_MS = 2 * 60 * 1000;
    const WARNING_TIME_MS = SESSION_TIMEOUT_MS - WARNING_BEFORE_MS;

    let activityTimer = null;
    let warningTimer = null;
    let warningModal = null;
    let countdownInterval = null;

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
            resetActivity();
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
        localStorage.clear();
        sessionStorage.clear();
        window.location.href = '/login';
    }

    function resetActivity() {
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
        const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
        events.forEach(function(event) {
            document.addEventListener(event, resetActivity, true);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setupActivityTracking();
            resetActivity();
        });
    } else {
        setupActivityTracking();
        resetActivity();
    }
})();
