"""
TechForge 3.0 — SMTP Email Service
Handles secure delivery of Jury credential provisioning emails.
"""

import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from flask import current_app

logger = logging.getLogger(__name__)


def get_smtp_config():
    """Retrieve SMTP configuration from Flask config or environment variables"""
    try:
        config = current_app.config
    except Exception:
        config = {}

    smtp_host = config.get('SMTP_HOST') or os.environ.get('SMTP_HOST', '')
    smtp_port = int(config.get('SMTP_PORT') or os.environ.get('SMTP_PORT', 587))
    smtp_username = config.get('SMTP_USERNAME') or os.environ.get('SMTP_USERNAME', '')
    smtp_password = config.get('SMTP_PASSWORD') or os.environ.get('SMTP_PASSWORD', '')
    smtp_from = config.get('SMTP_FROM') or os.environ.get('SMTP_FROM', 'techforge@srhu.edu.in')
    smtp_use_tls = str(config.get('SMTP_USE_TLS') or os.environ.get('SMTP_USE_TLS', 'true')).lower() in ['true', '1', 'yes']

    is_testing = bool(config.get('TESTING') or os.environ.get('TESTING') == 'True' or os.environ.get('SUPPRESS_EMAILS') == 'True')

    return {
        'host': smtp_host.strip(),
        'port': smtp_port,
        'username': smtp_username.strip(),
        'password': smtp_password,
        'from_addr': smtp_from.strip(),
        'use_tls': smtp_use_tls,
        'is_testing': is_testing,
        'is_configured': bool(smtp_host.strip() and smtp_username.strip())
    }


def send_jury_credentials_email(recipient_email, password, login_url=None, judge_name=None):
    """
    Send pre-provisioned Jury login credentials via SMTP email.
    
    Args:
        recipient_email (str): Target judge email address
        password (str): Generated temporary password
        login_url (str, optional): URL to the Jury Login page
        judge_name (str, optional): Judge's display name
        
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    cfg = get_smtp_config()
    name = judge_name or "Jury Member"
    url = login_url or "http://127.0.0.1:5002/judge/login"

    # Plain text email content
    plain_text = f"""Dear {name},

You have been registered as a Jury Member for:

TECHFORGE 3.0
School of Science & Technology
Swami Rama Himalayan University

Your Jury login credentials are:

Email:
{recipient_email}

Password:
{password}

Jury Login:
{url}

Please keep these credentials confidential.

Regards,
TechForge 3.0
School of Science & Technology
Swami Rama Himalayan University
"""

    # HTML email content with institutional branding
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px; color: #1e293b; }}
  .container {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
  .header {{ background: linear-gradient(135deg, #07192f 0%, #0d2e59 100%); padding: 28px 24px; text-align: center; color: #ffffff; }}
  .header h1 {{ margin: 0 0 4px; font-size: 22px; font-weight: 800; letter-spacing: 0.05em; }}
  .header p {{ margin: 0; font-size: 13px; opacity: 0.85; color: #93c5fd; }}
  .body {{ padding: 32px 28px; }}
  .credentials-box {{ background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 10px; padding: 20px; margin: 24px 0; }}
  .cred-row {{ margin-bottom: 12px; }}
  .cred-row:last-child {{ margin-bottom: 0; }}
  .cred-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 4px; }}
  .cred-value {{ font-family: 'Courier New', Courier, monospace; font-size: 16px; font-weight: 700; color: #0f172a; }}
  .pwd-highlight {{ color: #1a4d8f; font-size: 18px; }}
  .btn-login {{ display: inline-block; background: linear-gradient(135deg, #1a4d8f 0%, #0d2e59 100%); color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 700; font-size: 14px; margin-top: 16px; }}
  .footer {{ background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 24px; font-size: 12px; color: #64748b; text-align: center; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>TECHFORGE 3.0</h1>
      <p>Jury Evaluation Platform • School of Science & Technology (SRHU)</p>
    </div>
    <div class="body">
      <p style="margin-top: 0; font-size: 15px;">Dear <strong>{name}</strong>,</p>
      <p style="font-size: 14px; color: #475569; line-height: 1.5;">
        You have been registered as an official Jury Member for <strong>TechForge 3.0</strong>, the 36-Hours Internal Hackathon and SIH 2026 Institutional Selection Round.
      </p>
      
      <div class="credentials-box">
        <div class="cred-row">
          <div class="cred-label">Login Email</div>
          <div class="cred-value">{recipient_email}</div>
        </div>
        <div class="cred-row" style="margin-top: 12px;">
          <div class="cred-label">Temporary Password</div>
          <div class="cred-value pwd-highlight">{password}</div>
        </div>
      </div>

      <div style="text-align: center; margin: 24px 0;">
        <a href="{url}" class="btn-login">Open Jury Login Portal →</a>
      </div>

      <p style="font-size: 12px; color: #64748b; margin-bottom: 0;">
        ⚠️ Please keep these credentials confidential. You can log in using your email and password directly.
      </p>
    </div>
    <div class="footer">
      <strong>School of Science & Technology (SST)</strong><br>
      Swami Rama Himalayan University, Dehradun<br>
      <em>Inspiration: "Life Ka Compass"</em>
    </div>
  </div>
</body>
</html>
"""

    # If in testing mode or unconfigured SMTP, simulate clean delivery
    if cfg['is_testing'] or not cfg['is_configured']:
        return {'success': True, 'mode': 'simulated', 'recipient': recipient_email}

    # Live SMTP delivery
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header("TechForge 3.0 — Jury Login Credentials", 'utf-8')
        msg['From'] = f"TechForge 3.0 <{cfg['from_addr']}>"
        msg['To'] = recipient_email

        part1 = MIMEText(plain_text, 'plain', 'utf-8')
        part2 = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part1)
        msg.attach(part2)

        if cfg['use_tls']:
            server = smtplib.SMTP(cfg['host'], cfg['port'], timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(cfg['host'], cfg['port'], timeout=10)

        if cfg['username'] and cfg['password']:
            server.login(cfg['username'], cfg['password'])

        server.sendmail(cfg['from_addr'], [recipient_email], msg.as_string())
        server.quit()

        return {'success': True}

    except Exception:
        # Safe failure response without leaking SMTP passwords or stack traces
        return {'success': False, 'error': 'EMAIL_SEND_FAILED'}


def get_email_status():
    """Check email service health without exposing passwords"""
    cfg = get_smtp_config()
    return {
        'configured': cfg['is_configured'],
        'host': cfg['host'] or 'Not configured',
        'port': cfg['port'],
        'from_address': cfg['from_addr'],
        'use_tls': cfg['use_tls'],
        'is_testing': cfg['is_testing']
    }
