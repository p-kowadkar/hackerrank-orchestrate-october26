# Images and PDFs: what they show (read by hand, no LLM)

I opened all 11 PNGs and extracted all 4 PDFs (`pdftotext -layout`) myself. This file records what is
actually in them. Anything marked **derived** is my reading of the rules, not ground truth: none of
these cases has a sample answer.

Common facts:
- Every PNG is a clean, machine-rendered UI screenshot (no PNG metadata, no noise). Width 1800 px
  except `marketing_profile_console.png` (1500 px). Each shows a "Northstar Shop" header, a left nav,
  a table, a selected row, a detail panel and an activity timeline.
- Every PNG has exactly one **subject** row (highlighted, shown in the detail panel) plus decoy rows
  belonging to other people. The decoys sometimes reuse resource IDs from other cases.
- Who the subject is comes from the matching `LINK_RESOURCE_IDENTITY` event in `system_activity.csv`,
  not from the picture. Each LINK event is timestamped exactly capture time + 7m01s.
- Several screenshots show times later than the manifest `captured_at` (examples below). The manifest
  clock is what governs `audit_at` comparisons; the in-picture times are cosmetic.
- All 4 PDFs are ReportLab output, text-extractable, no OCR needed. PDF creation date (2026-10-23) is
  irrelevant; use the manifest `captured_at`.

## Images

### evidence_04 `account_admin_console_20260926.png` (captured 2026-09-26T11:00:00Z)
- App: Customer Operations > Customers. Customer **Haruka Sato** (Silver), `user_11 . account_5762`.
- Cards: email `haruka.s1838@zoho.com`; phone +81 90 7610 2507; signup mobile_app; market JP;
  language Japanese; last contact 24 Sep 2026 09:14 JST.
- Orders (2): ORD-20265762 (12 Sep, Ceramic coffee set, JPY 8,900, delivered 18 Sep);
  ORD-20265518 (28 Aug, Travel backpack, JPY 12,400, returned 03 Sep).
- Detail: default address 2-18-4 Kichijoji, Musashino, Tokyo; support CS-8538 . `support_9538`;
  member since 12 Jan 2024. Activity: 24 Sep customer replied to CS-8538; 22 Sep agent responded;
  18 Sep order delivered; 03 Sep order returned; 28 Aug `support_9538` created.
- LINK `activity_4000`: `account_5762` <-> `haruka.s1838@zoho.com` / `user_11`. Case: **case_34**
  (audit 2026-09-27T13:00).
- **Derived:** the account profile is live at 09-26. An older log (`evidence_01`, 09-15) says
  `account_5762` returned 404, so the account reappeared between those two captures. The newer
  direct evidence wins: REPORT_REMAINING_RECORD `account_service/account_5762`, cite `evidence_04`.
  `support_9538` is also exposed (`evidence_01` shows an attachment PII scan matching the user's old
  phone `+81 90 6156 0005`).

### evidence_09 `search_index_inspector_20260901.png` (captured 2026-09-01T06:00:00Z)
- App: Search Console > Customer Search. Query `email:g.silva76@gmail.com`, 2 hits, index
  `customer_directory_v3 / prod-eu`, executed 01 Sep 2026 06:00:14 UTC, latency 184 ms.
- Rows: **`search_428`** | Gabriel Silva | `g.silva76@gmail.com` | `user_13` | score 9.84 | indexed
  05:58:21 (selected). Decoy `search_1874` | no name | `g.silva76.jr@gmail.com` | no reference | 4.12.
- Raw document `search_428`: display_name Gabriel Silva, email, customer_reference `user_13`,
  indexed_at 2026-09-01T05:58:21Z. Activity lists unrelated queries (`user_9842`, "Aditi Jain").
- LINK `activity_4001`: `search_428` <-> `g.silva76@gmail.com` / `user_13`. Case: **case_35**
  (audit 2026-09-02T08:00).
- The decoy is a near-duplicate email belonging to someone else (same trap as sample case_28).
- **Derived:** search entry present -> REPORT_REMAINING_RECORD `search_service/search_428`
  -> DELETE_RECORD -> VERIFY_RECORD_ABSENT. Must not touch `search_1874`.

### evidence_14 `connector_management_console_20260807.png` (captured 2026-08-07T08:00:00Z)
- App: BridgeOps > Connections, PRODUCTION . eu-west . 07 Aug 2026 08:00 UTC, "12 connectors".
  Cards: healthy 12, events/hour 4,113, delivery p95 1.8 s, backlog 18, destination health Healthy.
- Rows: **`data_flow_1121`** | customer_analytics_warehouse | selector `jain.aditi@gmail.com` |
  Continuous | 1,284 events/h | last contact 07:59:42 (selected). Decoys: `data_flow_9846`
  (selector `lucia-torres@gmail.com`, 842/h, which is the subject flow of sample case_15), "Order
  notifications" -> notification_service, "Delivery tracking" -> logistics_warehouse.
- Detail `data_flow_1121`: Healthy; owner Data Platform; sync mode Continuous sync; last response
  200 OK . 1.8 s. Activity: 124 events delivered, checkpoint committed, 18 events retried.
- LINK `activity_4002`: `data_flow_1121` <-> `jain.aditi@gmail.com` / `user_14`. Case: **case_39**
  (audit 2026-08-08T10:00).
- **Derived:** flow is live and continuously syncing personal data to an analytics warehouse ->
  REPORT_ACTIVE_DATA_FLOW `integration_service/data_flow_1121` -> DISABLE_DATA_FLOW ->
  VERIFY_DATA_FLOW_DISABLED.

### evidence_19 `analytics_profile_view_20260713.png` (captured 2026-07-13T10:00:00Z)
- App: Pulse Analytics > Users. **Omar Darwish**, `user_20 . analytics_7438 . darwish.omar@icloud.com`,
  "Last 90 days". Sessions 12, products viewed 19, orders 2, revenue USD 167.42, mobile/desktop 67/33,
  acquisition Organic search.
- Timeline (5): 14:22 order completed (Ceramic coffee set, USD 84.21); 14:20 checkout started;
  14:17 product viewed; 14:16 added to cart; 14:12 product viewed (Stoneware mug).
  Attributes: market AE, audience Returning shopper, interest Coffee & dining,
  **last activity 13 Jul 2026 14:22 UTC** (later than the manifest capture time of 10:00), first seen 21 Apr.
- LINK `activity_4003`: `analytics_7438` <-> `darwish.omar@icloud.com` / `user_20`. Case: **case_50**
  (audit 2026-07-14T12:00).
- **Derived:** profile is attributable (name, email, user id on screen) -> REPORT_EXPOSED_PII
  `analytics_platform/analytics_7438` -> ANONYMIZE_RECORD (rule_07) -> VERIFY_RECORD_ANONYMIZED.

### evidence_23 `customer_export_console_20260618.png` (captured 2026-06-18T12:00:00Z)
- App: Customer Download Center > Data exports, 4 jobs. Cards: ready 2, processing 2, created today 1,
  downloads today 0.
- Rows: `export_1261` marcus.lee@northstar.shop Collecting (20 Jun 14:18, later than capture);
  **`export_1260`** `ingrid.dahl@outlook.com` Ready, created 18 Jun 06:42 (selected);
  `export_1259` sara.kim@northstar.shop Packaging; `export_1258` daniel.park@northstar.shop Ready.
- Detail `export_1260`: created 18 Jun 2026 06:42 UTC, **expires 25 Jun 2026 06:42 UTC**, 18.4 MB,
  SHA-256 `41ca09...`, download count 0, includes Profile . Orders . Saved addresses.
- LINK `activity_4004`: `export_1260` <-> `ingrid.dahl@outlook.com` / `user_18`. Cases: **case_52**
  (audit 2026-06-19T14:00) and **case_33** (audit 2026-07-19T13:00).
- **Derived (case_52):** export is Ready and unexpired at audit -> REPORT_REMAINING_RECORD
  `export_service/export_1260` -> DELETE_RECORD (rule_09) -> VERIFY_RECORD_ABSENT.
- **Open (case_33):** the 25 Jun expiry is before that audit date and nothing later (<= audit) says
  whether the file was removed or merely expired. `expires_at` vs `audit_at` has to be a stated rule.

### evidence_28 `support_ticket_console_20260524.png` (captured 2026-05-24T07:00:00Z)
- App: Helpline Console > Inbox. Ticket **CS-5034 "Where is my delivery?"**, `support_1034`,
  customer Kofi Agyeman, email `kagyeman8947@fastmail.com`, assigned Maya Chen, tags Delivery .
  Tracking . Order update, SLA 01:42.
- Conversation (4): customer asks where the order is; Northstar Bot acknowledges; agent Maya Chen says
  the parcel reached the regional hub, delivery on 26 May; customer thanks. Order panel ORD-20265034:
  Running shoes, In transit, SwiftShip, tracking SWF-884103, expected 26 May.
  Activity includes "24 May 08:15 In transit" (after capture time).
- LINK `activity_4005`: `support_1034` <-> `kagyeman8947@fastmail.com` / `user_22`. Case: **case_53**
  (audit 2026-05-25T09:00).
- **Derived:** a conversation holding the customer's identity *and* shared agent/order context.
  rule_05 (SUPPORT_MESSAGE) says keep the conversation and redact -> REPORT_EXPOSED_PII
  `support_platform/support_1034` -> REDACT_RECORD -> VERIFY_RECORD_REDACTED.

### evidence_32 `backup_restore_console_20260429.png` (captured 2026-04-29T09:00:00Z)
- App: Vault Recovery Manager > Recovery Manager, "Customer-platform archives" Healthy, weekly snapshots,
  restore success 99.6%, stored 1.35 PB.
- Rows: `backup_9291` bluepeakco@outlook.com; `backup_9288` miller.logistics@company.com;
  **`backup_9287`** `areed1433@gmail.com` eu-west-1, 84.7 GB, AES-256 (selected); `backup_9286`
  summit-retail@company.com. All created 26 Apr 02:00.
- Detail `backup_9287`: path `s3://northstar-backups/customer-platform/weekly/segment-42-20260426.tar.zst`,
  checksum Verified, last drill 29 Mar 2026, **retention end 26 Jul 2026**. Activity shows other
  archives being restored on 24-25 Apr. Nothing on screen says restore is blocked.
- LINK `activity_4006`: `backup_9287` <-> `areed1433@gmail.com` / `user_16`. Case: **case_55**
  (audit 2026-04-30T11:00).
- **Derived:** archive is retained (rule_14) but restore is not blocked ->
  REPORT_RESTORE_RISK `backup_service/backup_9287` -> BLOCK_RESTORE -> VERIFY_RESTORE_BLOCKED.
  (A `RESTORE_BACKUP` activity on 2026-08-22 later repopulates `search_4882` from this archive, but that
  is after this audit date.)

### evidence_37 `security_audit_explorer_20260905.png` (captured 2026-09-05T07:00:00Z)
- App: Sentinel > Account events, subject filter `user_03`, 18-26 Aug 2026, "6 signed events",
  integrity failures 0, partition 2026-Q3.
- Events: 25 Aug 04:03 Account closure recorded (`audit_record_003`, selected); 25 Aug 03:21 Session
  revoked (`002`); 24 Aug 16:14 Recovery challenge completed (`001`); 22 Aug 11:27 Email change
  confirmed (`006`); 20 Aug 09:42 Login from new device (`005`); 18 Aug 14:05 Password changed (`004`).
- Raw event `audit_record_003`: type account_closure_recorded, subject `user_03`, actor automated account
  workflow, recorded 2026-08-25T04:03:00Z, fingerprint `8f0c...31ad`, signature Valid, journal 2026-Q3.
- LINK `activity_4010`: `audit_record_003` <-> `oliver-bennett@gmail.com` / `user_03`. Case: **case_45**
  (audit 2026-09-06T09:00). Same record as PDF `evidence_55`.
- **Derived:** security audit log inside its retention period -> RETAIN (rule_12) ->
  VERIFY_RECORD_PRESENT `security_service/audit_record_003`. Unclear whether the five sibling events
  (`001`, `002`, `004`-`006`) also belong in the answer; only `003` is named by the LINK event and the PDF.

### evidence_42 `deleted_account_reference_20260310.png` (captured 2026-03-10T06:00:00Z)
- App: Customer Reference Registry > Customer references. Title **`user_17`**, badge "Retained
  reference", "Customer key . Account Platform . eu-west". Created 11 Jan 2024 08:42 UTC; most recent
  update 10 Mar 2026 07:18 UTC (after capture); owner team Account Platform.
- Linked records (all Active): Orders `ORD-20263245`; Support `CS-3245` and `CS-3378`; Finance
  `FIN-7742`. History: reference created 11 Jan 2024, support links Feb/Jun 2024, finance link
  22 Aug 2024, metadata reviewed 10 Mar 2026.
- No name, email, phone or hash anywhere on the page.
- LINK `activity_4011`: `tombstone_17` ("user_17") <-> `leonie.g9352@outlook.com` / `user_17`.
  Case: **case_46** (audit 2026-03-11T08:00).
- **Derived:** the tombstone holds only the stable key and the retained records still reference it ->
  compliant. VERIFY_RECORD_REDACTED `identity_service/tombstone_17` cites `evidence_42`.
  `evidence_67` (log, 03-10T06:18) shows `account_6523` -> 404 for the same email, so
  VERIFY_RECORD_ABSENT `account_service/account_6523` cites `evidence_67`. Likely COMPLETE.

### evidence_46 `object_storage_browser_20260213.png` (captured 2026-02-13T08:00:00Z)
- App: Nimbus Object Storage, bucket `northstar-customer-data`, path `eu-west-1 / support-attachments /
  2026 / 02`, 8 objects, captured 13 Feb 2026 08:00 UTC.
- Objects: **`delivery_confirmation_19.pdf`** 684 KB, modified 12 Feb 18:42, v3 (selected);
  `delivery_confirmation_20.pdf`; `return_label_4821.pdf`; `return_label_4876.pdf`;
  `invoice_NS-10493.pdf`; `parcel_damage_7713.jpg`; `customer_export_2026-02-10.zip`;
  `customer_export_2026-02-12.zip`.
- Detail: application/pdf, AES-256, checksum `e71b6d...`, uploader support-service. Versions v1 18:38
  created, v2 18:39 upload complete, v3 18:42 metadata update.
- LINK `activity_4007` says: "Attachment catalog confirmed `object_19` (delivery_confirmation_19.pdf)
  belongs only to `priya.raman@gmail.com` and `user_07`; no other subject is linked." Case: **case_61**
  (audit 2026-02-14T10:00). The sentence is the proof that rule_06's condition holds.
- **Derived:** attachment belongs only to the subject -> DELETE (rule_06): REPORT_REMAINING_RECORD
  `object_19`, DELETE_RECORD, VERIFY_RECORD_ABSENT. The `system_id` is probably `object_storage` (the LINK
  event's target system); no sample uses it, so that is unconfirmed.
- Timing trap: user_07's other attachment `support_001` (PDF `evidence_58`) was submitted 18 Jun 2026,
  after this audit date, so it must not appear in case_61. It belongs to sample case_07.

### evidence_60 `marketing_profile_console.png` (captured 2026-09-16T07:20:00Z)
- App: Audience Operations. Header **Soo-jin Park**, badge Live, `marketing_001 . sj.park@naver.com .
  +82 10-5837-9451`. Market South Korea, language Korean, email opt-in Yes, SMS opt-in No, last
  refreshed 15 Sep 2026 23:40 UTC. Audience "Returning customers - East Asia", segments Repeat customer .
  Home & lifestyle . Mobile shopper, categories Desk accessories . Drinkware, last campaign Autumn
  offers, open rate 32.4%, click rate 6.8%.
- LINK `activity_4008`: `marketing_001` <-> **`kwame-mensah@proton.me` / `user_09`**.
  Case: **case_63** (audit 2026-09-17T09:20).
- **Mismatch:** the person on screen (Soo-jin Park, naver email, Korean phone) appears nowhere in
  `user_identities.csv`; `user_09` is Kwame Mensah (Ghana). Trust the LINK event for identity and use the
  screenshot only for "a live marketing profile `marketing_001` exists".
- **Derived:** MARKETING_PROFILE present -> REPORT_REMAINING_RECORD `marketing_platform/marketing_001`
  -> DELETE_RECORD (rule_10) -> VERIFY_RECORD_ABSENT.

## PDFs

### evidence_18 `account_history_report_20260718.pdf` (captured 2026-07-18T11:00:00Z, 2 pages)
- Customer statement **NST-2026-0718-1842**: customer Ingrid Dahl, `user_18`, `ingrid.dahl@outlook.com`,
  order ORD-20261260 (Smart desk lamp SKU LAMP-SD-04, qty 1, subtotal EUR 54.95, shipping 4.99, tax
  11.99, total EUR 71.93), Visa ending 4821, paid, ordered 08 Jul, dispatched 10 Jul, delivered 14 Jul.
  Page 2: delivery address 24 Fjordgata, 7010 Trondheim, Norway.
- LINK `activity_4009`: `export_1842` (NST-2026-0718-1842) <-> Ingrid Dahl / `user_18`. Case: **case_33**
  (audit 2026-07-19T13:00). The statement number's suffix is the export id.
- **Derived:** the statement is a downloadable user export holding PII -> REPORT_REMAINING_RECORD
  `export_service/export_1842` -> DELETE_RECORD -> VERIFY_RECORD_ABSENT.

### evidence_58 `delivery_correction_attachment.pdf` (captured 2026-09-12T07:30:00Z, 2 pages)
- Delivery address correction request, support ref **CS-4827 / `support_001`**, received 18 Jun 2026,
  Priya Raman, `priya.raman@gmail.com`, +91 98765 73142, order ORD-20264827, preferred contact SMS,
  request "change apartment number from 14B to 18B and call before delivery", Stainless steel water
  bottle x2, SwiftShip. Page 2: file `delivery_address_correction.pdf`, 312 KB, ticket CS-4827,
  region ap-south, uploader customer, captured 12 Sep 2026 07:30 UTC, checksum prefix c90a42.
- **Used by sample case_07** (REPORT_REMAINING_RECORD `support_platform/support_001`, cite
  `evidence_58`). It is the customer's own attachment, so rule_06 DELETE applies. Confirms the PDF is
  a direct state proof and the in-text email is the link (no LINK event needed).

### evidence_27 `legal_retention_register_20260529.pdf` (captured 2026-05-29T08:00:00Z, 2 pages)
- "Disputed orders and tax records register", Finance Operations, May 2026, classification Internal.
  Page 1 holds a template instruction line ("For each row add invoice date, finance owner, retain-until
  date, and case/reference number"). Page 2 lists 6 rows: ORD-20264118 `user_08` card dispute, retain
  until 04 May 2033; ORD-20264207 `user_12` tax correction, 2033; ORD-20264319 `user_17` chargeback,
  2033; ORD-20264402 `user_21` invoice inquiry, 2033; ORD-20264511 `user_24` card dispute, 2033;
  ORD-20264600 `user_29` tax record, 2033.
- No `legal_hold_*` resource ids appear. All six users are sample users whose sample answers contain
  no legal-service step. So a register row by itself does **not** create a legal-hold step. The real
  `legal_hold_*` records appear only in eval-only evidence (bundles `evidence_45`/`evidence_40`,
  manifest `evidence_36`, ops stream `evidence_21`) and in 10 `RETAIN_RECORD -> legal_service` events.
- **Status: unresolved.** Treat as context/decoy until an eval-only case shows how a hold is expressed.

### evidence_55 `security_retention_extract.pdf` (captured 2026-09-05T06:30:00Z, 1 page)
- "Compliance Journal - signed record extract", ref CJX-20260905-0630, Internal Restricted, issued
  05 Sep 2026 06:30 UTC. Event reference **`audit_record_003`**, subject `user_03`, "Account closure
  recorded", actor automated account workflow, recorded 25 Aug 2026 04:03 UTC, **retain until
  25 Aug 2027 04:03 UTC**, partition 2026-Q3, version 1, storage class compliance-ledger, integrity
  seal valid, fingerprint `8f0c...31ad`.
- Same record as image `evidence_37`. It is the only artifact that states the retention end date.
- Case: **case_45**. Both files are <= audit (09-05T06:30 and 09-05T07:00 vs audit 09-06T09:00); the
  later capture (`evidence_37`) is the one the "latest <= audit_at" citation rule picks.

## Derived expectations for the 12 image/PDF cases (unverified, for tests and discussion)

| case | audit_at | artifact(s) <= audit | subject | derived verdict and core steps |
|---|---|---|---|---|
| 33 | 07-19T13:00 | evidence_18 (+23) | `export_1842` | INCOMPLETE: finding/delete/verify-absent `export_1842`; `export_1260` unclear (expired 06-25) |
| 34 | 09-27T13:00 | evidence_04 (newer than log 404 in evidence_01) | `account_5762`, `support_9538` | INCOMPLETE: account reappeared; delete account and attachment |
| 35 | 09-02T08:00 | evidence_09 | `search_428` | INCOMPLETE: delete search entry; ignore decoy `search_1874` |
| 39 | 08-08T10:00 | evidence_14 | `data_flow_1121` | INCOMPLETE: disable flow, verify disabled |
| 45 | 09-06T09:00 | evidence_37, evidence_55 | `audit_record_003` | COMPLETE: verify present (retained) |
| 46 | 03-11T08:00 | evidence_42, evidence_67 | `tombstone_17`, `account_6523` | COMPLETE: absent account, redacted tombstone |
| 50 | 07-14T12:00 | evidence_19 | `analytics_7438` | INCOMPLETE: anonymize, verify anonymized |
| 52 | 06-19T14:00 | evidence_23 | `export_1260` | INCOMPLETE: delete export, verify absent |
| 53 | 05-25T09:00 | evidence_28 | `support_1034` | INCOMPLETE: redact (not delete), verify redacted |
| 55 | 04-30T11:00 | evidence_32 | `backup_9287` | INCOMPLETE: block restore, verify blocked |
| 61 | 02-14T10:00 | evidence_46 | `object_19` | INCOMPLETE: delete attachment |
| 63 | 09-17T09:20 | evidence_60 | `marketing_001` | INCOMPLETE: delete marketing profile |

For each case the golden answer probably also carries the user's account (VERIFY_RECORD_ABSENT) and,
where one exists, the audit record (VERIFY_RECORD_PRESENT). For these 12 cases those IDs are visible
only in *later* evidence (`evidence_01`, 09-15, or `evidence_02`, 09-17), which is fine for identity
but not for state or citation. The three users with more than one case (user_07, user_17, user_18)
need per-case scoping so one case's resources do not leak into the other's.
