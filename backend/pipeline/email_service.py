import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_DEV_LABELS = {
    "WRONG_SOURCE":          "Wrong Source",
    "PLANT_MISMATCH":        "Plant Mismatch",
    "DELAYED":               "Past Due",
    "DELAY_FLAG":            "Pre-Flagged",
    "MISSING_CRITICAL_STEP": "Missing Critical Step",
    "OUT_OF_SEQUENCE":       "Out of Sequence",
    "DUPLICATE_STEP":        "Duplicate Step",
}

# OFI brand colours
_DARK   = "#242424"
_GOLD   = "#cca23f"
_WHITE  = "#ffffff"
_LIGHT  = "#f2f2f2"


def _strip_html(s: str) -> str:
    """Remove simple HTML tags for plain-text fallback."""
    import re
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return s


def _build_group_html(deviation_type: str, group: dict, today: str):
    """
    Build OFI-branded HTML email + plain-text fallback for a group alert.
    Returns (subject, html_body, plain_text).
    """
    key       = group.get("key", "")
    count     = group.get("count", 0)
    pct       = group.get("pct", 0)
    pct_disp  = group.get("pct_display") or f"{pct}%"
    dev_label = _DEV_LABELS.get(deviation_type, deviation_type.replace("_", " ").title())

    # ── Type-specific narrative ───────────────────────────────────────────────
    if deviation_type == "WRONG_SOURCE":
        actual  = group.get("actual_source") or key.split("→")[0].strip() if "→" in key else "Unknown"
        optimal = group.get("optimal_source") or (key.split("→")[1].strip() if "→" in key else "")
        heading = f"Wrong Source Alert — {key}"
        issue   = (
            f"Orders are being dispatched from <strong>{actual}</strong>"
            + (f" instead of the designated optimal source <strong>{optimal}</strong>."
               if optimal else ", which does not match the optimal source location on record.")
        )
        impact  = (
            f"This routing deviation affects <strong>{count:,} orders</strong> "
            f"({pct_disp} of all Wrong Source cases). "
            f"Non-optimal sourcing drives unnecessary transport cost, increases lead time variability, "
            f"and creates SLA breach exposure across affected deliveries."
        )
        action  = (
            f"1. Review dispatch assignments originating from <strong>{actual}</strong>.<br>"
            + (f"2. Redirect eligible future orders through the designated source <strong>{optimal}</strong>.<br>"
               if optimal else "2. Identify and configure the correct source in the logistics system.<br>")
            + f"3. Investigate whether this pattern is a systemic data issue or an operational decision — "
            + f"if intentional, escalate for a formal exception approval."
        )
        who = "Logistics Operations Manager"

    elif deviation_type == "DELAYED":
        heading = f"Delivery Delay Alert — {key}"
        issue   = f"<strong>{count:,} orders</strong> have breached their scheduled delivery date, falling in the delay band: <strong>{key}</strong>."
        impact  = (
            f"These orders ({pct_disp} of all past-due cases) carry active SLA breach risk. "
            f"Each additional day of delay compounds customer impact and increases the likelihood "
            f"of formal penalty claims or contract review."
        )
        action  = (
            "1. Escalate all orders in this delay band to the logistics coordination team immediately.<br>"
            "2. Prioritise expedited processing and notify downstream stakeholders of revised ETAs.<br>"
            "3. Conduct a root cause review — if this band is recurring, address the upstream scheduling process."
        )
        who = "Logistics Coordination / Customer Service Lead"

    elif deviation_type == "DELAY_FLAG":
        heading = "Pre-Flagged Delay Risk Alert"
        issue   = (
            f"<strong>{count:,} orders</strong> have been pre-flagged by the source system "
            f"as at risk of missing their delivery deadline."
        )
        impact  = (
            "Early-flagged orders have a high conversion rate to confirmed delays without intervention. "
            "Addressing them now is significantly cheaper — in both cost and customer relationship terms — "
            "than managing confirmed SLA breaches after the fact."
        )
        action  = (
            "1. Identify which flagged orders are closest to their delivery deadline and prioritise those first.<br>"
            "2. Engage upstream suppliers or production teams to expedite where possible.<br>"
            "3. Where expediting is not feasible, notify customers proactively with a revised date."
        )
        who = "Supply Chain / Customer Service Manager"

    elif deviation_type == "MISSING_CRITICAL_STEP":
        step    = group.get("missing_step", key)
        heading = f"Missing Critical Step — '{step}'"
        issue   = (
            f"<strong>{count:,} orders</strong> completed without the mandatory process step: "
            f"<strong>{step}</strong>."
        )
        impact  = (
            f"Missing steps create audit exposure, incomplete operational records, and potential "
            f"compliance failures. This pattern accounts for {pct_disp} of all missing-step cases "
            f"and may indicate a systemic bypass or training gap in the team handling these orders."
        )
        action  = (
            f"1. Confirm whether these orders genuinely skipped <strong>{step}</strong> or if it was logged incorrectly.<br>"
            f"2. For any orders where the step was genuinely skipped, determine corrective action (e.g. retroactive processing, exception sign-off).<br>"
            f"3. Identify the root cause: system bypass, team training gap, or process exception — and close the gap."
        )
        who = "Operations / Process Compliance Manager"

    elif deviation_type == "PLANT_MISMATCH":
        actual   = group.get("actual_plant") or key.split("→")[0].strip() if "→" in key else "Unknown"
        required = group.get("required_plant") or (key.split("→")[1].strip() if "→" in key else "")
        heading  = f"Plant Mismatch Alert — {key}"
        issue    = (
            f"Orders are being processed at <strong>{actual}</strong>"
            + (f" instead of the required plant <strong>{required}</strong>." if required else ".")
        )
        impact   = (
            f"{count:,} orders ({pct_disp} of plant mismatch cases) are processed at a non-designated "
            f"facility. This may violate production routing rules, cause quality or traceability issues, "
            f"and create downstream audit risk."
        )
        action   = (
            f"1. Review whether routing to <strong>{actual}</strong> was an approved exception or an error.<br>"
            + (f"2. Identify orders that can still be redirected to <strong>{required}</strong> without further delay.<br>"
               if required else "")
            + "3. Update plant routing rules and communicate the correct assignment to the planning team."
        )
        who = "Production Planning / Operations Manager"

    else:
        heading = f"{dev_label} — {key}"
        issue   = f"<strong>{count:,} orders</strong> have a confirmed <strong>{dev_label}</strong> compliance deviation."
        impact  = (
            f"This pattern accounts for {pct_disp} of {dev_label} cases in the current analysis period. "
            f"Unchecked, it will continue to grow and may trigger audit findings or customer escalations."
        )
        action  = (
            "1. Review the full list of affected orders in the PCA system.<br>"
            "2. Apply corrective action per your standard compliance procedure.<br>"
            "3. Set a review date to confirm resolution within 5 business days."
        )
        who = "Compliance / Operations Manager"

    subject = f"[OFI Compliance] {heading} — {count:,} Orders Require Attention"

    html = _build_ofi_html(
        subject=subject, dev_label=dev_label, heading=heading, who=who,
        issue=issue, impact=impact, action=action,
        count=count, kpi_mid_val=pct_disp, kpi_mid_lbl=f"of {dev_label} Cases", today=today,
    )

    plain = f"""{subject}
{"=" * min(len(subject), 72)}

{heading}
Deviation type   : {dev_label}
Orders affected  : {count:,} ({pct_disp} of {dev_label} cases)
Escalate to      : {who}
Date             : {today}

SITUATION
---------
{_strip_html(issue)}

BUSINESS IMPACT
---------------
{_strip_html(impact)}

ACTION REQUIRED
---------------
{_strip_html(action)}

Log in to the PCA system to view and action all {count:,} affected orders.

---
Generated by OFI Process Compliance Agent  |  {today}
"""

    return subject, html, plain


def build_group_alert(deviation_type: str, group: dict, today: str):
    """Return (subject, html_body, plain_text) for a compliance group alert."""
    return _build_group_html(deviation_type, group, today)


def send_group_alert(deviation_type: str, group: dict, today: str) -> dict:
    """Build and send OFI-branded HTML group alert. Returns status dict."""
    smtp_user  = os.getenv("SMTP_USER", "")
    smtp_pass  = os.getenv("SMTP_PASS", "")
    to_email   = os.getenv("ALERT_TO_EMAIL", "")

    subject, html_body, plain_body = build_group_alert(deviation_type, group, today)

    if not smtp_user or not smtp_pass or not to_email:
        return {
            "status": "no_smtp",
            "subject": subject,
            "html_body": html_body,
            "body": plain_body,
            "recipient": to_email,
        }

    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))
    from_email = os.getenv("ALERT_FROM_EMAIL", smtp_user)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_email
        msg["To"]      = to_email
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())

        logger.info("Group alert sent: %s → %s", subject, to_email)
        return {
            "status": "sent",
            "subject": subject,
            "html_body": html_body,
            "body": plain_body,
            "recipient": to_email,
        }
    except Exception as e:
        logger.error("Group alert send failed: %s", e)
        return {
            "status": "error",
            "subject": subject,
            "html_body": html_body,
            "body": plain_body,
            "recipient": to_email,
        }


def _build_ofi_html(subject: str, dev_label: str, heading: str, who: str,
                    issue: str, impact: str, action: str,
                    count: int, kpi_mid_val: str, kpi_mid_lbl: str, today: str) -> str:
    """Shared OFI HTML email renderer used by all alert builders."""
    kpi_cell = f"padding:14px 18px;background:{_DARK};border-radius:4px;text-align:center;width:33%;"
    kpi_val  = f"font-size:20px;font-weight:800;color:{_GOLD};"
    kpi_lbl  = f"font-size:10px;color:rgba(255,255,255,0.5);letter-spacing:1.2px;text-transform:uppercase;margin-top:6px;"

    kpi_block = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;border-collapse:separate;border-spacing:8px 0;">
<tr>
  <td style="{kpi_cell}">
    <div style="{kpi_val}">{count:,}</div>
    <div style="{kpi_lbl}">Orders Affected</div>
  </td>
  <td style="{kpi_cell}">
    <div style="{kpi_val}">{kpi_mid_val}</div>
    <div style="{kpi_lbl}">{kpi_mid_lbl}</div>
  </td>
  <td style="{kpi_cell}">
    <div style="{kpi_val}">{today}</div>
    <div style="{kpi_lbl}">Reported Date</div>
  </td>
</tr>
</table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:{_LIGHT};font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{_LIGHT};padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
  style="background:{_WHITE};border-radius:4px;overflow:hidden;box-shadow:0 2px 14px rgba(0,0,0,0.12);">
  <tr>
    <td style="background:{_DARK};padding:22px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td>
          <span style="color:{_GOLD};font-size:21px;font-weight:700;letter-spacing:2px;">OFI</span>
          <div style="color:rgba(255,255,255,0.45);font-size:10px;letter-spacing:2.5px;text-transform:uppercase;margin-top:4px;">Process Compliance Agent</div>
        </td>
        <td align="right">
          <span style="background:{_GOLD};color:{_DARK};font-size:10px;font-weight:700;padding:5px 13px;border-radius:11px;letter-spacing:0.5px;text-transform:uppercase;">Compliance Alert</span>
        </td>
      </tr></table>
    </td>
  </tr>
  <tr>
    <td style="background:#1c1c1c;border-left:4px solid {_GOLD};padding:14px 32px;">
      <div style="color:{_GOLD};font-size:10px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;margin-bottom:4px;">{dev_label}</div>
      <div style="color:{_WHITE};font-size:17px;font-weight:600;">{heading}</div>
      <div style="color:rgba(255,255,255,0.4);font-size:12px;margin-top:5px;">Action required &nbsp;&middot;&nbsp; Escalate to: {who}</div>
    </td>
  </tr>
  <tr><td style="padding:28px 32px 24px;">
    <p style="margin:0 0 6px 0;font-size:10px;font-weight:700;color:{_GOLD};letter-spacing:1.5px;text-transform:uppercase;">Situation</p>
    <p style="margin:0 0 16px 0;font-size:14px;color:#333;line-height:1.8;">{issue}</p>
    {kpi_block}
    <div style="border-top:1px solid #ebebeb;margin:20px 0;"></div>
    <p style="margin:0 0 6px 0;font-size:10px;font-weight:700;color:{_GOLD};letter-spacing:1.5px;text-transform:uppercase;">Business Impact</p>
    <p style="margin:0 0 24px 0;font-size:13px;color:#555;line-height:1.8;">{impact}</p>
    <div style="border-top:1px solid #ebebeb;margin:0 0 20px 0;"></div>
    <p style="margin:0 0 8px 0;font-size:10px;font-weight:700;color:{_GOLD};letter-spacing:1.5px;text-transform:uppercase;">Action Required</p>
    <p style="margin:0 0 20px 0;font-size:14px;color:#333;line-height:2.2;">{action}</p>
    <table cellpadding="0" cellspacing="0" style="margin:8px 0 4px;">
      <tr>
        <td style="background:{_DARK};border-radius:4px;padding:11px 24px;">
          <span style="color:{_GOLD};font-size:13px;font-weight:700;letter-spacing:0.5px;">Log in to PCA to view &amp; action all {count:,} orders →</span>
        </td>
      </tr>
    </table>
  </td></tr>
  <tr>
    <td style="background:{_DARK};padding:18px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td><span style="color:rgba(255,255,255,0.35);font-size:11px;">Generated by OFI Process Compliance Agent &nbsp;&middot;&nbsp; Do not reply.</span></td>
        <td align="right"><span style="color:{_GOLD};font-size:11px;font-weight:700;letter-spacing:1px;">OFI SERVICES</span></td>
      </tr></table>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def build_context_alert(
    order_count: int,
    today: str,
    deviation_type: str | None = None,
    group_key: str | None = None,
    intersection_filters: list[str] | None = None,
    status: str | None = None,
    risk: str | None = None,
) -> tuple[str, str, str]:
    """
    Build OFI-branded alert for any Orders-page filter context.
    Returns (subject, html_body, plain_text).
    """

    # ── Case 1: Cross-filter intersection ────────────────────────────────────
    if intersection_filters and len(intersection_filters) >= 2:
        labels = []
        for f in intersection_filters:
            if ":" in f:
                ftype, fkey = f.split(":", 1)
                labels.append(f"{_DEV_LABELS.get(ftype, ftype)}: {fkey}")

        filter_html  = "<br>".join(f"&nbsp;&nbsp;• <strong>{l}</strong>" for l in labels)
        filter_plain = " AND ".join(labels)

        heading   = f"Multi-Issue Compliance Alert — {order_count:,} Orders"
        dev_label = "Multiple Issues"
        who       = "Compliance Manager / Cross-functional Team"
        issue     = (
            f"<strong>{order_count:,} orders</strong> simultaneously have ALL of the following "
            f"compliance issues:<br>{filter_html}"
        )
        impact    = (
            f"Orders with multiple simultaneous compliance failures are your highest-priority risk. "
            f"Each additional issue compounds the others — wrong-source routing that is also delayed "
            f"carries both excess logistics cost AND active SLA breach exposure in a single order. "
            f"These {order_count:,} orders require immediate coordinated action across the responsible teams."
        )
        action_items = [f"Prioritise these <strong>{order_count:,} orders</strong> for immediate cross-team review."]
        for l in labels:
            action_items.append(f"Resolve <strong>{l}</strong> per standard compliance procedure for that issue type.")
        action_items.append("Confirm full resolution across all issues within 48 hours.")
        action = "<br>".join(f"{i + 1}. {item}" for i, item in enumerate(action_items))
        kpi_mid_val = str(len(labels))
        kpi_mid_lbl = "Issues Combined"

    # ── Case 2: Specific group (deviation_type + group_key) ─────────────────
    elif deviation_type and group_key:
        group = {"key": group_key, "count": order_count, "pct": 0, "pct_display": f"{order_count:,}"}
        return _build_group_html(deviation_type, group, today)

    # ── Case 3: Full deviation type (no group key) ───────────────────────────
    elif deviation_type:
        dev_label = _DEV_LABELS.get(deviation_type, deviation_type.replace("_", " ").title())
        heading   = f"{dev_label} Alert — {order_count:,} Orders"
        who       = "Compliance / Operations Manager"
        issue     = (
            f"<strong>{order_count:,} orders</strong> have a confirmed "
            f"<strong>{dev_label}</strong> compliance deviation."
        )
        impact    = (
            f"This deviation type affects a significant portion of your order volume. "
            f"Unresolved {dev_label.lower()} cases accumulate cost, audit exposure, and "
            f"customer relationship risk with every additional day without action."
        )
        action    = (
            f"1. Review all {order_count:,} affected orders in the PCA system.<br>"
            f"2. Apply corrective action per your standard {dev_label} compliance procedure.<br>"
            f"3. Set a review date within 5 business days to confirm resolution."
        )
        kpi_mid_val = dev_label
        kpi_mid_lbl = "Deviation Type"

    # ── Case 4: Status / risk filter ─────────────────────────────────────────
    else:
        s = (status or "").upper()
        r = (risk  or "").upper()
        if s == "BLOCKED" and r:
            heading   = f"BLOCKED / {r} Risk Orders — {order_count:,} Orders"
            dev_label = f"BLOCKED · {r} RISK"
            issue     = (
                f"<strong>{order_count:,} orders</strong> are currently blocked with "
                f"<strong>{r} risk</strong> classification in the compliance system."
            )
            kpi_mid_val = f"{s} / {r}"
        elif s == "BLOCKED":
            heading   = f"Blocked Orders Alert — {order_count:,} Orders"
            dev_label = "BLOCKED ORDERS"
            issue     = f"<strong>{order_count:,} orders</strong> are currently blocked from the normal fulfilment process."
            kpi_mid_val = "BLOCKED"
        elif s == "ALERT":
            heading   = f"Alert-Status Orders — {order_count:,} Orders"
            dev_label = "ALERT STATUS"
            issue     = f"<strong>{order_count:,} orders</strong> are in ALERT status and require timely review."
            kpi_mid_val = "ALERT"
        elif r:
            heading   = f"{r} Risk Orders — {order_count:,} Orders"
            dev_label = f"{r} RISK"
            issue     = f"<strong>{order_count:,} orders</strong> carry <strong>{r} risk</strong> classification."
            kpi_mid_val = f"{r} RISK"
        else:
            heading   = f"Compliance Review — {order_count:,} Orders"
            dev_label = "SELECTED ORDERS"
            issue     = f"<strong>{order_count:,} orders</strong> meet the current filter criteria and require review."
            kpi_mid_val = "REVIEW"

        who    = "Compliance Manager"
        impact = (
            f"Blocked and high-risk orders are stalled in the compliance process until deviations "
            f"are resolved. Each day of inaction increases the probability of SLA breaches, "
            f"audit findings, and escalating customer dissatisfaction."
        )
        action = (
            "1. Review all affected orders in the PCA Action Center.<br>"
            "2. Assign each order to the appropriate team owner for corrective action.<br>"
            "3. Target full resolution within 3–5 business days."
        )
        kpi_mid_lbl = "Filter Applied"

    subject = f"[OFI Compliance] {heading}"

    html = _build_ofi_html(
        subject=subject, dev_label=dev_label, heading=heading, who=who,
        issue=issue, impact=impact, action=action,
        count=order_count, kpi_mid_val=kpi_mid_val, kpi_mid_lbl=kpi_mid_lbl, today=today,
    )

    plain = f"""{subject}
{"=" * min(len(subject), 72)}

{heading}
Deviation context: {dev_label}
Orders affected  : {order_count:,}
Escalate to      : {who}
Date             : {today}

SITUATION
---------
{_strip_html(issue)}

BUSINESS IMPACT
---------------
{_strip_html(impact)}

ACTION REQUIRED
---------------
{_strip_html(action)}

Log in to the PCA system to view and action all {order_count:,} affected orders.

---
Generated by OFI Process Compliance Agent  |  {today}
"""
    return subject, html, plain


def send_context_alert(
    order_count: int,
    today: str,
    deviation_type: str | None = None,
    group_key: str | None = None,
    intersection_filters: list[str] | None = None,
    status: str | None = None,
    risk: str | None = None,
) -> dict:
    """Build and send context alert. Returns status dict."""
    smtp_user  = os.getenv("SMTP_USER", "")
    smtp_pass  = os.getenv("SMTP_PASS", "")
    to_email   = os.getenv("ALERT_TO_EMAIL", "")

    subject, html_body, plain_body = build_context_alert(
        order_count=order_count, today=today,
        deviation_type=deviation_type, group_key=group_key,
        intersection_filters=intersection_filters, status=status, risk=risk,
    )

    if not smtp_user or not smtp_pass or not to_email:
        return {"status": "no_smtp", "subject": subject, "html_body": html_body,
                "body": plain_body, "recipient": to_email}

    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))
    from_email = os.getenv("ALERT_FROM_EMAIL", smtp_user)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_email
        msg["To"]      = to_email
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo(); server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        logger.info("Context alert sent: %s → %s", subject, to_email)
        return {"status": "sent", "subject": subject, "html_body": html_body,
                "body": plain_body, "recipient": to_email}
    except Exception as e:
        logger.error("Context alert send failed: %s", e)
        return {"status": "error", "subject": subject, "html_body": html_body,
                "body": plain_body, "recipient": to_email}


def _build_order_html(order: dict) -> str:
    order_num  = order.get("Order_Number", "N/A")
    status     = order.get("Process_Status", "")
    risk       = order.get("Risk_Level", "")
    score      = order.get("Deviation_Score", 0)
    deviations = order.get("Deviations", [])
    root_cause = order.get("root_cause", "")
    recommendation = order.get("recommendation", "")

    dev_rows = "".join(
        f'<tr style="border-bottom:1px solid #eeeeee;">'
        f'<td style="padding:7px 14px;font-size:13px;color:{_DARK};">{d.get("type","")}</td>'
        f'<td style="padding:7px 14px;font-size:13px;">{d.get("severity","")}</td>'
        f'<td style="padding:7px 14px;font-size:13px;color:#666;">{d.get("detail","")}</td>'
        f'</tr>'
        for d in deviations
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:{_LIGHT};font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:{_LIGHT};padding:32px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
  style="background:{_WHITE};border-radius:4px;overflow:hidden;box-shadow:0 2px 14px rgba(0,0,0,0.12);">
  <tr>
    <td style="background:{_DARK};padding:22px 32px;">
      <span style="color:{_GOLD};font-size:21px;font-weight:700;letter-spacing:2px;">OFI</span>
      <div style="color:rgba(255,255,255,0.45);font-size:10px;letter-spacing:2.5px;text-transform:uppercase;margin-top:4px;">
        Process Compliance Agent
      </div>
    </td>
  </tr>
  <tr>
    <td style="background:#1c1c1c;border-left:4px solid {_GOLD};padding:14px 32px;">
      <div style="color:{_GOLD};font-size:10px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase;">
        Order Alert — {status}
      </div>
      <div style="color:{_WHITE};font-size:16px;font-weight:600;margin-top:4px;">
        Order {order_num} &nbsp;&middot;&nbsp; Risk: {risk} &nbsp;&middot;&nbsp; Score: {score}
      </div>
    </td>
  </tr>
  <tr><td style="padding:28px 32px;">
    {"<p style='font-size:14px;color:#333;line-height:1.7;'><strong>Root Cause:</strong> " + root_cause + "</p>" if root_cause else ""}
    {"<p style='font-size:14px;color:#333;line-height:1.7;'><strong>Recommendation:</strong> " + recommendation + "</p>" if recommendation else ""}
    <p style="margin:0 0 8px 0;font-size:10px;font-weight:700;color:{_GOLD};letter-spacing:1.5px;text-transform:uppercase;">
      Detected Deviations
    </p>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e8e8e8;">
      <thead>
        <tr style="background:{_DARK};">
          <th style="padding:9px 14px;text-align:left;color:{_GOLD};font-size:11px;font-weight:700;text-transform:uppercase;">Type</th>
          <th style="padding:9px 14px;text-align:left;color:{_GOLD};font-size:11px;font-weight:700;text-transform:uppercase;">Severity</th>
          <th style="padding:9px 14px;text-align:left;color:{_GOLD};font-size:11px;font-weight:700;text-transform:uppercase;">Detail</th>
        </tr>
      </thead>
      <tbody>{dev_rows}</tbody>
    </table>
  </td></tr>
  <tr>
    <td style="background:{_DARK};padding:18px 32px;">
      <span style="color:rgba(255,255,255,0.35);font-size:11px;">
        Generated by OFI Process Compliance Agent &nbsp;&middot;&nbsp; Do not reply.
      </span>
    </td>
  </tr>
</table>
</td></tr>
</table>
</body></html>"""


def send_alerts_for_blocked(orders: list[dict]) -> list[str]:
    """Send OFI-branded HTML alert emails for each BLOCKED or HIGH-risk order."""
    smtp_host  = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port  = int(os.getenv("SMTP_PORT", "587"))
    smtp_user  = os.getenv("SMTP_USER", "")
    smtp_pass  = os.getenv("SMTP_PASS", "")
    from_email = os.getenv("ALERT_FROM_EMAIL", smtp_user)
    to_email   = os.getenv("ALERT_TO_EMAIL", "")

    if not smtp_user or not smtp_pass or not to_email:
        logger.warning("Email alerts skipped — SMTP credentials not configured in .env")
        return []

    targets = [
        o for o in orders
        if o.get("Process_Status") == "BLOCKED" or o.get("Risk_Level") in ("CRITICAL", "HIGH")
    ]

    sent = []
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            for order in targets:
                order_num = order.get("Order_Number", "N/A")
                msg = MIMEMultipart("alternative")
                msg["Subject"] = (
                    f"[OFI Compliance] {order.get('Process_Status')} Order {order_num} "
                    f"— Risk: {order.get('Risk_Level')}"
                )
                msg["From"] = from_email
                msg["To"]   = to_email
                msg.attach(MIMEText(_build_order_html(order), "html"))
                server.sendmail(from_email, to_email, msg.as_string())
                sent.append(str(order_num))
                logger.info("Alert sent for order %s", order_num)
    except Exception as e:
        logger.error("Failed to send alert emails: %s", e)

    return sent
