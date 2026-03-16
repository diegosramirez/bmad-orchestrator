# Initiative: Affiliate Link Sharing via Mobile (THIS IS FOR DESKTOP TOO, NOT JUST MOBILE)

## Pitch

## Problem

Vendors have contacts who would make great affiliates, but the path from "I want to share my link" to a sent message is too long: open dashboard → copy link → switch apps → type message → paste → send. Every extra step bleeds conversion. On mobile — where these moments of inspiration happen (post-event, on a train) — the friction is especially high.
What specific friction or gap exists today? Which persona feels it most? Include data if available.

## Bet

Add an "Invite Affiliates" button per product in the vendor dashboard that generates a pre-written message with the affiliate join link and opens the native share sheet via the Web Share API. Vendors go from idea to sent WhatsApp message in under 30 seconds. We're betting this removes enough friction to measurably grow affiliate registrations per vendor.
Note: No existing KR covers this today; it can be tracked as a standalone leading indicator.
Why Now
The implementation is likely to be frontend work, purely client-side, zero backend changes, and zero risk to existing flows. The Web Share API is now supported on >90% of active mobile browsers. The cost of waiting is a continued drop-off every time a vendor has a warm contact and no easy way to act on it.
Expected Outcome

Shape Doc — Slice 1: Mobile Affiliate Invite
Written after Pitch approval. Covers this slice only. Reviewed by founder alongside prototype before any code is written. Once approved, this section is the PRD fed to BMAD.
What We're Building
Today, vendors who want to recruit affiliates must manually copy their join link from the dashboard, switch to WhatsApp or another app, write a message, paste the link, and send. On mobile this takes 60–90 seconds minimum and most vendors don't bother.
In this slice: we add an "Invite Affiliates" button on each product card in the vendor dashboard (only shown when an affiliate join link exists for that product). Tapping it shows a pre-written message preview with the product name, commission rate, and the affiliate join link pre-filled. The vendor taps Share → native share sheet opens → they pick WhatsApp, SMS, or any other app → done. On browsers without Web Share API support, a "Copy Message" clipboard fallback is shown instead. All share and copy events are tracked in PostHog.
Nothing is sent to Digistore servers. No backend changes. No new dependencies.
Target Persona
Primary: Vendor — online course creator, coach, or info product seller with an existing personal network (seminar contacts, masterminds, social connections) who wants to grow their affiliate base from their phone.
Also affected: Prospective affiliates who receive the message (existing affiliate join flow handles their onboarding — no changes needed in this slice).

User Journeys
Journey 1 — Thomas: Shares affiliate invites on mobile, happy path
Who: Thomas (38), online marketing coach, sells 3 courses on Digistore. Broad warm network from seminars and masterminds.
Scenario: Thomas is on a train after a mastermind weekend. He opens Digistore on his phone, navigates to his top course "Facebook Ads Masterclass," and sees the "Invite Affiliates" button. He taps it. A message preview appears: "Hey, I have an online course on Digistore — 40% commission per sale. You can sign up as an affiliate here: [link]." He taps Share. The native share sheet opens. He selects 12 WhatsApp contacts and sends. Total time: under 30 seconds.
What must be true:
The "Invite Affiliates" button is visible on each product that has an affiliate join link (FR1, FR10)
A pre-written message is generated from product name, commission rate, and affiliate join link (FR5, FR6)
A message preview is shown before sharing (FR7)
Tapping Share opens the native Web Share API share sheet (FR3)
A "Share completed" event is logged in PostHog (FR13)

Journey 2 — Thomas: Web Share API not available (fallback)
Who: Thomas, same context, but using an older Android browser without Web Share API support.
Scenario: Thomas taps "Invite Affiliates" on his older Android browser. The system detects that Web Share API is unavailable. Instead of the share sheet, the message appears as selectable text with a prominent "Copy Message" button. Thomas taps Copy, switches to WhatsApp manually, pastes, selects contacts, sends. It takes 10 seconds longer, but it works.
What must be true:
System detects Web Share API availability via navigator.share (FR8)
Clipboard fallback is shown when Web Share API is not supported (FR4, FR9)
A confirmation is shown after successful copy (FR11)
A "Share completed" event is still logged (FR13)

Journey 3 — Thomas: Invites for multiple products
Who: Thomas, 3 courses on Digistore, wants different affiliates for different products.
Scenario: Thomas goes to Course 1 → taps "Invite Affiliates" → shares with 12 contacts. He goes back to his dashboard, opens Course 2, taps "Invite Affiliates" — the message now shows Course 2's name and commission rate and a different join link. He shares with a different set of contacts.
What must be true:
Each product has its own "Invite Affiliates" button (FR1)
The message and link are product-specific (FR6)
Button is hidden for products without an affiliate join link (FR10)

MVP Scope
In scope:
Not in this slice:
Contact import or CRM integration
Server-side SMS sending
Tracking who received the message
Message editor (vendor customises copy)
Desktop-optimised flow
Analytics dashboard for vendors
Explicit list. Anything not listed here will be assumed in scope.
Risks:

Functional Requirements

Non-Functional Requirements

Design & Prototype
Figma: [Link — PM to add]
Loom walkthrough: [Link — PM to add]

PostHog Tracking Plan
Feature flag: affiliate_mobile_invite Variants: control, invite_button

Testing & Rollout
Completed by PM + EM before this slice ships. Not delegated.
Avatar walkthrough:
Regression check:
Rollout:
Rollback SLA: 5 minutes — Trigger: Error rate >1% on share flow OR any regression in product dashboard

Agent Handoff
Fill in with EM before handing to BMAD. Everything the agent needs to build this slice without follow-up questions.
Stack:
Backend: PHP
Frontend: [React / Angular — confirm with Shawn]
Component library: [Link]
Relevant files / components: [List or link — e.g. product card component, dashboard view]
Build summary: [Write here]
Plain language. What already exists, what is net new, which FRs to implement.
Must not change:
[Write here]
Explicit list of existing functionality the agent must leave untouched.
Definition of done:
All FRs implemented and verified
All NFRs met
Unit + E2E tests written
PostHog events firing in all variants
control variant confirmed working
PM + EM avatar walkthrough signed off

Comms
Internal (Hermes): [Link — published when slice ships]
External (Hermes): [Link — published when slice ships; this feature stands alone]

Open Questions

Results
Filled in after the full bet ships. Not closed until release notes are published.
What Shipped
[Write here]
Results vs. Targets
What We Learned
[Write here]
Next Bet
[Write here]
Release Notes
Internal (Hermes): [Link]
External (Hermes): [Link]
