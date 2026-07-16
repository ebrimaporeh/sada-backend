"""Seed markdown content for LegalContent — transcribed as-is from the
frontend's previously-hardcoded Help/Trust & Safety/Privacy/Terms pages,
so switching those pages over to admin-editable markdown doesn't change
what's shown until an admin actually edits something. The platform fee
mentions below reflect PlatformSettings' default of 1% at the time of
writing — editable here going forward like the rest of the page.
"""

DEFAULT_HELP_CONTENT = """### How do I start a campaign?
Create a free account, click "Start a Campaign", and fill in your campaign details — title, story, goal, and deadline. Your campaign goes live immediately, no waiting on approval.

### What fees does GambiaFund charge?
Donations carry no GambiaFund fee — donors only pay whatever their mobile money provider itself charges. A 1% platform fee applies only when a campaign owner withdraws raised funds.

### How do I donate to a campaign?
Find a campaign you want to support, click "Donate Now", enter your amount and mobile money number, then confirm the payment prompt on your phone. Your donation is recorded as soon as the payment clears.

### Which mobile money networks are supported?
We currently support Wave and APS Wallet, both through the ModemPay payment gateway.

### When can I withdraw raised funds?
You can request a withdrawal at any time once your campaign has received donations. Go to your campaign management page, open the Withdraw tab, and submit a withdrawal request.

### How long does a withdrawal take?
Withdrawals are typically processed within 1–3 business days. You will receive a notification once the funds are sent to your mobile money account.

### Can I donate anonymously?
Yes. When donating, check the "Donate anonymously" option. Your name will not be shown publicly on the campaign page, though the donation amount is still counted.

### What happens if a campaign doesn't reach its goal?
GambiaFund uses a keep-it-all model. Campaign owners receive all funds raised regardless of whether the goal is met.

### How do I update or pause my campaign?
Go to "My Campaigns", select your campaign, and open the Edit tab. From there you can update your campaign details, upload new photos, post updates for donors, or pause the campaign temporarily.

### How do I get my identity verified?
From your Profile page, submit a government-issued ID (national ID, passport, or driver's license). An admin reviews it, and once approved your account shows a verified badge."""

DEFAULT_TRUST_SAFETY_CONTENT = """## Campaign Review
Every campaign submitted to GambiaFund is reviewed by our moderation team. We verify that the campaign story is genuine, the beneficiary information is plausible, and the fundraising goal is appropriate. Campaigns that do not meet our standards are suspended with a reason provided to the organiser.

## Secure Payments
All donations are processed through ModemPay, a licensed mobile money gateway covering Wave and APS Wallet. GambiaFund never stores your payment credentials. Payment confirmations happen directly between your mobile network and ModemPay — we only record the result.

## Donor Protection
We display the full fundraising history and withdrawal records for every campaign so donors can see exactly how money is being used. Campaign owners can verify their identity with a government ID for an added trust badge.

## Reporting Abuse
If you believe a campaign is fraudulent or violates our policies, use the Report button on the campaign page. Our team reviews every report and will suspend any campaign found to be in violation.

## Contact Our Trust Team
For urgent concerns, reach us through the Help Center below. We aim to respond to trust and safety reports promptly."""

DEFAULT_PRIVACY_CONTENT = """## What We Collect
- Account information — name, email address, phone number, and profile photo when you register.
- Campaign information — title, story, images, beneficiary details, and fundraising goal that you provide when creating a campaign.
- Donation records — amount, payment provider, timestamp, and optional message for each donation made through the platform.
- Usage data — pages visited, device type, and browser to help us improve the platform. We do not use third-party advertising trackers.

## How We Use It
- To operate your account and process donations.
- To review and moderate campaigns submitted to the platform.
- To send you notifications about your campaigns, donations, and withdrawals.
- To detect and prevent fraud and abuse.
- We do not sell your personal data to third parties.

## Who We Share It With
- ModemPay — your mobile number and donation amount are shared to process payments.
- Our moderation team — campaign details may be reviewed if a campaign is reported.
- Law enforcement — only when required by law or to protect users from harm.

## Donor Visibility
- By default, your name and donation amount are shown on the campaign page.
- You can choose to donate anonymously — your name will be hidden from the public campaign page.
- Your contact details are never visible to campaign owners.

## Data Retention
- Account data is retained for as long as your account is active.
- Donation and withdrawal records are kept for 7 years for financial compliance.
- You may request deletion of your account by emailing privacy@gambiafund.gm. Legally required financial records will be retained even after deletion.

## Your Rights
- You may request a copy of the personal data we hold about you.
- You may correct inaccurate information from your account settings at any time.
- You may request deletion of your account and associated data.
- To exercise any of these rights, email privacy@gambiafund.gm.

## Contact
- Questions about this policy? Email privacy@gambiafund.gm.
- Last updated: June 2026."""

DEFAULT_TERMS_CONTENT = """## 1. Acceptance
By using GambiaFund you agree to these Terms of Service. If you do not agree, please do not use the platform. We may update these terms from time to time and will notify users of material changes.

## 2. Eligibility
You must be at least 18 years old to create a campaign or make a donation. By registering, you confirm that you are 18 or older and that the information you provide is accurate.

## 3. Campaign Rules
Campaign owners are responsible for the accuracy of all information provided. Campaigns must have a genuine, lawful purpose. The following are prohibited: false or misleading campaigns, campaigns that promote violence, illegal activity, or discrimination, and campaigns where the stated beneficiary has not consented. Campaigns go live immediately on creation; GambiaFund reserves the right to suspend or remove any campaign that violates these rules at any time.

## 4. Fees
Donations carry no GambiaFund fee — donors only pay whatever their mobile money provider itself charges to process the payment. A 1% platform fee is deducted only when a campaign owner withdraws raised funds. Fees are clearly disclosed before each withdrawal is confirmed.

## 5. Withdrawals
Campaign owners may withdraw funds at any time. GambiaFund reserves the right to hold funds pending investigation if fraud is suspected. Funds held as part of an active investigation may not be released until the investigation is resolved.

## 6. Donor Obligations
Donations are voluntary and generally non-refundable once processed. If you believe a donation was made in error or to a fraudulent campaign, use the Report button on the campaign page and we will investigate.

## 7. Intellectual Property
You retain ownership of content you upload (photos, campaign stories). By uploading content, you grant GambiaFund a non-exclusive licence to display that content on the platform for the purpose of operating the service.

## 8. Limitation of Liability
GambiaFund is a platform that facilitates fundraising. We do not guarantee that campaign goals will be reached or that funds will be used as stated by campaign owners. We are not liable for losses arising from fraudulent campaigns beyond the funds held in our systems at the time a complaint is raised.

## 9. Governing Law
These terms are governed by the laws of The Gambia. Any disputes shall be resolved in the courts of The Gambia."""
