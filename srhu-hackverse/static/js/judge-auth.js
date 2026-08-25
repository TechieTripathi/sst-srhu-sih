/**
 * TechForge 3.0 — Jury OTP Authentication Handler
 * Handles two-step email + OTP verification, auto-focus, paste handling, and countdowns.
 */

document.addEventListener('DOMContentLoaded', function() {
    const emailStep = document.getElementById('emailStep');
    const otpStep = document.getElementById('otpStep');
    const emailForm = document.getElementById('emailForm');
    const otpForm = document.getElementById('otpForm');
    const judgeEmailInput = document.getElementById('judgeEmail');
    const sendOtpBtn = document.getElementById('sendOtpBtn');
    const verifyOtpBtn = document.getElementById('verifyOtpBtn');
    const alertBox = document.getElementById('alertBox');
    const alertMessage = document.getElementById('alertMessage');
    const maskedEmailTarget = document.getElementById('maskedEmailTarget');
    const changeEmailBtn = document.getElementById('changeEmailBtn');
    const resendOtpBtn = document.getElementById('resendOtpBtn');
    const resendCountdown = document.getElementById('resendCountdown');
    const otpInputs = document.querySelectorAll('.otp-box-input');

    let currentEmail = '';
    let countdownInterval = null;
    let resendSeconds = 45;

    function showAlert(message, type = 'danger') {
        alertBox.className = `auth-alert alert-${type}`;
        alertMessage.textContent = message;
        alertBox.style.display = 'flex';
    }

    function hideAlert() {
        alertBox.style.display = 'none';
        alertMessage.textContent = '';
    }

    function setBtnLoading(button, isLoading, originalText) {
        if (isLoading) {
            button.disabled = true;
            button.dataset.orig = originalText;
            button.innerHTML = `<span class="spinner"></span> Processing...`;
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.orig || originalText;
        }
    }

    function startResendCountdown(seconds = 45) {
        if (countdownInterval) clearInterval(countdownInterval);
        resendSeconds = seconds;
        resendOtpBtn.disabled = true;
        resendCountdown.style.display = 'inline';
        resendCountdown.textContent = `(${resendSeconds}s)`;

        countdownInterval = setInterval(() => {
            resendSeconds--;
            if (resendSeconds <= 0) {
                clearInterval(countdownInterval);
                resendOtpBtn.disabled = false;
                resendCountdown.style.display = 'none';
            } else {
                resendCountdown.textContent = `(${resendSeconds}s)`;
            }
        }, 1000);
    }

    // --- STEP 1: Request OTP ---
    async function handleRequestOtp(e) {
        if (e) e.preventDefault();
        hideAlert();

        const email = judgeEmailInput.value.trim().toLowerCase();
        if (!email || !email.includes('@')) {
            showAlert('Please enter a valid official email address.', 'danger');
            judgeEmailInput.focus();
            return;
        }

        setBtnLoading(sendOtpBtn, true, 'Send OTP');

        try {
            const res = await fetch('/api/auth/judge/request-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            });

            const data = await res.json();

            if (res.ok && data.success) {
                currentEmail = email;
                maskedEmailTarget.textContent = data.masked_email || email;
                
                // Switch to OTP view
                emailStep.style.display = 'none';
                otpStep.style.display = 'block';
                
                // Clear OTP inputs
                otpInputs.forEach(input => input.value = '');
                if (otpInputs[0]) otpInputs[0].focus();

                startResendCountdown(data.cooldown_seconds || 45);
            } else {
                showAlert(data.message || 'Unable to send OTP. Please check your email.', 'danger');
            }
        } catch (err) {
            showAlert('A network error occurred. Please try again.', 'danger');
        } finally {
            setBtnLoading(sendOtpBtn, false, 'Send OTP');
        }
    }

    if (emailForm) {
        emailForm.addEventListener('submit', handleRequestOtp);
    }

    // --- STEP 2: OTP 6-Box Inputs Handling ---
    otpInputs.forEach((input, index) => {
        // Auto-advance
        input.addEventListener('input', (e) => {
            const val = e.target.value;
            // Clean non-numeric
            e.target.value = val.replace(/\D/g, '');

            if (e.target.value.length >= 1) {
                e.target.value = e.target.value.charAt(0);
                if (index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
            }
        });

        // Backspace
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !input.value && index > 0) {
                otpInputs[index - 1].focus();
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                handleVerifyOtp();
            }
        });

        // Paste support
        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasteData = (e.clipboardData || window.clipboardData).getData('text').trim().replace(/\D/g, '');
            if (pasteData.length >= 6) {
                for (let i = 0; i < 6; i++) {
                    if (otpInputs[i]) {
                        otpInputs[i].value = pasteData.charAt(i);
                    }
                }
                otpInputs[5].focus();
            } else if (pasteData.length > 0) {
                for (let i = 0; i < pasteData.length && (index + i) < otpInputs.length; i++) {
                    otpInputs[index + i].value = pasteData.charAt(i);
                }
                const nextIndex = Math.min(index + pasteData.length, otpInputs.length - 1);
                otpInputs[nextIndex].focus();
            }
        });
    });

    // --- STEP 3: Verify OTP ---
    async function handleVerifyOtp(e) {
        if (e) e.preventDefault();
        hideAlert();

        let otpCode = '';
        otpInputs.forEach(input => otpCode += input.value.trim());

        if (otpCode.length !== 6) {
            showAlert('Please enter the complete 6-digit OTP.', 'danger');
            return;
        }

        setBtnLoading(verifyOtpBtn, true, 'Verify & Login');

        try {
            const res = await fetch('/api/auth/judge/verify-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: currentEmail,
                    otp: otpCode
                })
            });

            const data = await res.json();

            if (res.ok && data.success) {
                showAlert('Login successful! Redirecting to your Jury Dashboard...', 'success');
                setTimeout(() => {
                    window.location.href = data.redirect_url || '/judge/dashboard';
                }, 600);
            } else {
                showAlert(data.message || 'Invalid or expired OTP. Please try again.', 'danger');
                otpInputs.forEach(input => input.value = '');
                if (otpInputs[0]) otpInputs[0].focus();
            }
        } catch (err) {
            showAlert('A network error occurred during verification. Please try again.', 'danger');
        } finally {
            setBtnLoading(verifyOtpBtn, false, 'Verify & Login');
        }
    }

    if (otpForm) {
        otpForm.addEventListener('submit', handleVerifyOtp);
    }

    // Change Email Click
    if (changeEmailBtn) {
        changeEmailBtn.addEventListener('click', () => {
            hideAlert();
            if (countdownInterval) clearInterval(countdownInterval);
            otpStep.style.display = 'none';
            emailStep.style.display = 'block';
            judgeEmailInput.focus();
        });
    }

    // Resend OTP Click
    if (resendOtpBtn) {
        resendOtpBtn.addEventListener('click', () => {
            if (resendSeconds <= 0 || resendOtpBtn.disabled === false) {
                handleRequestOtp();
            }
        });
    }
});
