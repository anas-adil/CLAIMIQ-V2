"""
claims_processor.py (v2) — 8-Step Claim Processing Pipeline

Orchestrates the full v2 pipeline:
1. Scrubbing (Validation rules)
2. Eligibility (Coverage check)
3. Document Extraction (GLM)
4. Clinical Validation (GLM)
5. Medical Coding (GLM)
6. Adjudication / RAG (GLM)
7. Fraud Detection (GLM)
8. GP Advisory (GLM)
+ EOB Generation
"""

import sys, os, json, logging, time, uuid

sys.path.insert(0, os.path.dirname(__file__))

import glm_client
import database as db
import rag_engine
import claim_scrubber
import eligibility_engine
import eob_generator
import evidence_parser
import cross_reference_engine
import denial_predictor
import fraud_graph
import drg_mapper
import disposition_engine

logger = logging.getLogger("claimiq.processor")

def process_claim(claim_id: int = None, raw_text: str = None) -> dict:
    """Run the full claim pipeline and persist decision artifacts."""
    claim = None
    if claim_id is not None and claim_id <= 0:
        raise ValueError("claim_id must be a positive integer")
    if claim_id:
        claim = db.get_claim(claim_id)
        if not claim: raise ValueError(f"Claim {claim_id} not found")
        # Prefer explicit raw_text when supplied, otherwise use persisted claim payload.
        raw_text = raw_text or claim["raw_text"]
    elif raw_text and not claim_id:
        claim_id = db.insert_claim(raw_text)
        claim = db.get_claim(claim_id)
    else:
        raise ValueError("Must provide either claim_id or raw_text")
    
    if not db.acquire_processing_lock(claim_id):
        raise ValueError(f"Claim {claim_id} is already being processed")

    try:
        db.update_claim(claim_id, status="PROCESSING", lifecycle_stage="PROCESSING")
        processing_run_id = f"run-{claim_id}-{uuid.uuid4().hex[:12]}"
        result = {"claim_id": claim_id, "processing_run_id": processing_run_id, "steps": {}}
        pipeline_findings = []
        start_time = time.time()

        try:
            # Step 3: Extraction (Needed first to get data for Scrub/Eligibility)
            logger.info(f"[{claim_id}] Step 3: Extracting claim data...")
            extracted = glm_client.extract_claim_data(raw_text, claim_id=claim_id)

            # Merge patient-submitted fields (from initial claim submission) as ground truth.
            # These were stored in extracted_data during submit_claim and should NOT be
            # overwritten by LLM extraction or mock fallback.
            initial_data_str = claim.get("extracted_data") if claim else None
            initial_data = {}
            if initial_data_str:
                try:
                    initial_data = json.loads(initial_data_str) if isinstance(initial_data_str, str) else initial_data_str
                    # Priority fields from submission override LLM extraction
                    for key in [
                        "patient_name",
                        "patient_ic",
                        "clinic_name",
                        "visit_date",
                        "total_amount_myr",
                        "_vision_analysis",
                        "_vision_source",
                    ]:
                        if initial_data.get(key):
                            extracted[key] = initial_data[key]
                except (json.JSONDecodeError, TypeError):
                    initial_data = {}

            # Preserve evidence payload for downstream parsing and potential reprocessing.
            for key in ["_evidence_base64", "_invoice_base64", "_bill_attached", "_evidence_attached"]:
                if initial_data.get(key):
                    extracted[key] = initial_data[key]

            extracted["raw_text"] = raw_text
            # Use submitted claim record as source-of-truth for critical fields whenever present.
            if claim and claim.get("visit_date"):
                extracted["visit_date"] = claim.get("visit_date")
            if claim and claim.get("total_amount_myr") is not None:
                extracted["total_amount_myr"] = claim.get("total_amount_myr")
            try:
                extracted["total_amount_myr"] = float(extracted.get("total_amount_myr") or 0.0)
            except (TypeError, ValueError):
                extracted["total_amount_myr"] = 0.0
            db.update_claim(
                claim_id, extracted_data=json.dumps(extracted),
                patient_name=extracted.get("patient_name"), patient_ic=extracted.get("patient_ic"),
                clinic_name=extracted.get("clinic_name"), diagnosis=extracted.get("diagnosis"),
                total_amount_myr=extracted.get("total_amount_myr"), visit_date=extracted.get("visit_date")
            )
            result["steps"]["extraction"] = extracted

            # Step 3.5: Evidence Parsing
            logger.info(f"[{claim_id}] Step 3.5: Parsing evidence with MedGemma...")
            evidence_b64 = extracted
            parsed_evidence_list = []
            if evidence_b64:
                try:
                    initial_data = json.loads(evidence_b64) if isinstance(evidence_b64, str) else evidence_b64
                    if "_evidence_base64" in initial_data and initial_data["_evidence_base64"]:
                        parsed = evidence_parser.parse_evidence(initial_data["_evidence_base64"])
                        parsed_evidence_list.append(parsed)
                    if "_invoice_base64" in initial_data and initial_data["_invoice_base64"]:
                        parsed = evidence_parser.parse_evidence(initial_data["_invoice_base64"])
                        parsed_evidence_list.append(parsed)
                        
                    if parsed_evidence_list:
                        db.update_claim(claim_id, parsed_evidence=json.dumps(parsed_evidence_list),
                                        evidence_doc_type=parsed_evidence_list[0].get("triage", {}).get("doc_type"),
                                        evidence_quality=parsed_evidence_list[0].get("triage", {}).get("quality"))
                except Exception as e:
                    logger.error(f"Failed to parse evidence: {e}")
                    # Preserve a non-empty parse record so deterministic gates know
                    # attachments were present but parser runtime failed.
                    if initial_data.get("_evidence_base64") or initial_data.get("_invoice_base64"):
                        parsed_evidence_list.append({
                            "source": "PARSE_RUNTIME_FAILED",
                            "parsing_confidence": 0.0,
                            "triage": {"doc_type": "UNKNOWN", "quality": "UNKNOWN"},
                            "parsed_evidence": {"error": str(e)},
                        })
            
            # Step 3.6: Evidence Quality & Completeness Gate
            logger.info(f"[{claim_id}] Step 3.6: Checking evidence completeness...")
            total_amt = extracted.get("total_amount_myr", 0)
            
            has_invoice = any(ev.get("triage", {}).get("doc_type") == "INVOICE" for ev in parsed_evidence_list)
            has_clinical_evidence = any(ev.get("triage", {}).get("doc_type") in ("LAB_REPORT", "XRAY") for ev in parsed_evidence_list)
            
            # Check image quality
            poor_quality_ev = [ev for ev in parsed_evidence_list if ev.get("triage", {}).get("quality") in ("POOR", "BLURRY", "SUSPECT")]
            for ev in poor_quality_ev:
                pipeline_findings.append({
                    "severity": "WARN",
                    "source": "EVIDENCE_QUALITY",
                    "detail": f"Evidence quality warning: {ev.get('triage', {}).get('quality')} - {', '.join(ev.get('triage', {}).get('warnings', []))}"
                })
                
            if total_amt > 1000:
                if not has_invoice or not has_clinical_evidence:
                    pipeline_findings.append({
                        "severity": "CRITICAL",
                        "source": "MISSING_EVIDENCE",
                        "detail": f"⚠️ SAFETY GATE: High-cost claim (RM {total_amt}) requires both an itemized invoice and clinical evidence (lab report/X-ray). Insufficient evidence attached.",
                        "carc": "16"
                    })
                    
            if len(parsed_evidence_list) == 0 and total_amt > 500:
                pipeline_findings.append({
                    "severity": "CRITICAL",
                    "source": "MISSING_EVIDENCE",
                    "detail": f"⚠️ SAFETY GATE: Claim over RM 500 requires supporting evidence documents. None attached.",
                    "carc": "16"
                })

            # Step 3.7: Cross-Reference Gate
            logger.info(f"[{claim_id}] Step 3.7: Cross-referencing evidence...")
            cross_ref = cross_reference_engine.cross_reference_all(parsed_evidence_list, extracted, raw_text)
            result["steps"]["cross_reference"] = cross_ref
            db.update_claim(claim_id, cross_ref_result=json.dumps(cross_ref))
            result["steps"]["deterministic_validation"] = cross_ref.get("deterministic_summary", {})

            if cross_ref["verdict"] == "FAIL" and cross_ref.get("critical_count", 0) > 0:
                logger.warning(f"[{claim_id}] CROSS-REFERENCE GATE: {cross_ref['critical_count']} critical contradictions found")
                
                fraud_flags = []
                for chk in cross_ref.get("checks", []):
                    fraud_flags.append({
                        "flag_type": "EVIDENCE_CONTRADICTION",
                        "description": chk.get("note", "Evidence contradicts clinical description"),
                        "severity": 0.95,
                        "evidence": f"Doctor says {chk.get('field','?')}: {chk.get('doctor_says','?')} | "
                                    f"Lab/Invoice shows: {chk.get('lab_shows', chk.get('invoice_shows', '?'))}"
                    })
                fraud_data = {
                    "fraud_risk_score": 0.95,
                    "risk_level": "CRITICAL",
                    "flags": fraud_flags,
                    "recommendation": "INVESTIGATE",
                }
                db.insert_fraud_score(claim_id, fraud_data)
                db.update_claim(claim_id, fraud_flagged=1)
                
                contradiction_notes = "; ".join(
                    str(chk.get("note") or "Contradiction detected")
                    for chk in (cross_ref.get("checks") or [])
                )
                pipeline_findings.append({
                    "severity": "CRITICAL",
                    "source": "CROSS_REFERENCE",
                    "detail": f"⚠️ FRAUD ALERT: {contradiction_notes}"
                })

            # Stage-2 gating: critical deterministic mismatches force manual review.
            validation_findings = cross_ref.get("validation_findings", [])
            critical_validation = [
                f for f in validation_findings
                if f.get("severity") == "CRITICAL"
                and f.get("type") in ("IDENTITY_MISMATCH", "DATE_MISMATCH")
            ]
            for f in critical_validation:
                pipeline_findings.append({
                    "severity": "CRITICAL",
                    "source": "VALIDATION",
                    "detail": f.get("note", "Critical claim/evidence mismatch detected."),
                    "carc": "16",
                })

            # Step 1: Scrubbing
            logger.info(f"[{claim_id}] Step 1: Scrubbing claim...")
            scrub = claim_scrubber.scrub_claim(extracted, claim_id)
            db.update_claim(claim_id, scrub_result=json.dumps(scrub))
            result["steps"]["scrub"] = scrub
            if scrub["status"] == "FAIL":
                pipeline_findings.append({
                    "severity": "CRITICAL",
                    "source": "SCRUBBER",
                    "detail": scrub["errors"][0]["message"],
                    "carc": scrub["errors"][0].get("carc", "16")
                })
            elif scrub["status"] == "WARN":
                pipeline_findings.append({
                    "severity": "WARN",
                    "source": "SCRUBBER",
                    "detail": scrub["warnings"][0]["message"]
                })

            # Step 2: Eligibility
            logger.info(f"[{claim_id}] Step 2: Checking eligibility...")
            ic = extracted.get("patient_ic", "") or (claim.get("patient_ic", "") if claim else "")
            visit_date = (claim.get("visit_date", "") if claim else "") or extracted.get("visit_date", "")
            amount = (claim.get("total_amount_myr", 0) if claim else 0) or extracted.get("total_amount_myr", 0)
            eligibility = (
                eligibility_engine.check_eligibility(ic, visit_date, amount, claim_id=claim_id)
                if ic else
                eligibility_engine.simulate_eligibility_for_unknown(amount)
            )
            db.update_claim(claim_id, eligibility_result=json.dumps(eligibility))
            result["steps"]["eligibility"] = eligibility
            if not eligibility["eligible"]:
                pipeline_findings.append({
                    "severity": "CRITICAL",
                    "source": "ELIGIBILITY",
                    "detail": eligibility["message"],
                    "carc": eligibility.get("carc_code", "27")
                })

            # Phase-1 deterministic disposition hard gates (can finalize before LLM).
            disposition = disposition_engine.evaluate_phase1_disposition(
                claim_record=claim,
                extracted=extracted,
                cross_ref=cross_ref,
                eligibility=eligibility,
                parsed_evidence_list=parsed_evidence_list,
            )
            result["steps"]["disposition"] = disposition
            # Record disposition findings but do NOT return early — let the full
            # GLM pipeline run so rich adjudication reasoning, fraud analysis,
            # GP advisory, and EOB are always generated for every claim.
            if disposition.get("finalize_now"):
                for h in disposition.get("rule_hits", []):
                    pipeline_findings.append({
                        "severity": "CRITICAL",
                        "source": "DISPOSITION",
                        "detail": f"{h.get('rule_id')}: {h.get('reason')}",
                        "carc": h.get("carc", "16"),
                    })

            # Step 4: Clinical Validation
            logger.info(f"[{claim_id}] Step 4: Clinical Validation...")
            clinical_val = glm_client.validate_claim_pre_adjudication(extracted, claim_id=claim_id)
            result["steps"]["validation"] = clinical_val

            # Step 5: Coding
            logger.info(f"[{claim_id}] Step 5: Medical Coding...")
            coded = glm_client.assign_medical_codes(extracted, claim_id=claim_id)
            db.update_claim(claim_id, coded_data=json.dumps(coded), icd10_code=coded.get("primary_diagnosis_code"))
            result["steps"]["coding"] = coded
            result["steps"]["drg"] = drg_mapper.map_icd_to_drg(coded.get("primary_diagnosis_code"))
            full_claim = {**extracted, **coded}
            # Re-assert authoritative amount — coding response must never override the
            # submitted total (live LLM sometimes hallucinate 0 for this field).
            _auth_amount = (
                float(claim["total_amount_myr"])
                if claim and claim.get("total_amount_myr") is not None
                else float(extracted.get("total_amount_myr") or 0)
            )
            full_claim["total_amount_myr"] = _auth_amount

            if parsed_evidence_list:
                full_claim["_parsed_evidence"] = parsed_evidence_list
            full_claim["_cross_reference_result"] = cross_ref
            full_claim["_validation_result"] = {
                "summary": cross_ref.get("deterministic_summary", {}),
                "findings": validation_findings,
            }

            # Step 6: Adjudication — attach full raw_text (incl. evidence packet) for GLM reasoning
            logger.info(f"[{claim_id}] Step 6: Policy Adjudication...")
            policy_context = rag_engine.get_policy_context(extracted)
            full_claim_with_evidence = {**full_claim, "_raw_evidence_packet": raw_text}
            decision = glm_client.adjudicate_claim(full_claim_with_evidence, policy_context, claim_id=claim_id)
            if not isinstance(decision, dict):
                decision = {}
            # Normalize common model key drift so downstream logic doesn't lose decision context.
            if not decision.get("decision"):
                decision["decision"] = (
                    decision.get("result")
                    or decision.get("final_decision")
                    or decision.get("adjudication_decision")
                    or "REFERRED"
                )
            if decision.get("confidence") is None:
                decision["confidence"] = decision.get("adjudication_confidence")
            if decision.get("confidence") is None:
                decision["confidence"] = 0.65
            if not str(decision.get("reasoning") or "").strip():
                for alias in (
                    "reason", "explanation", "rationale", "processing_notes",
                    "analysis", "adjudication_reasoning", "detailed_reasoning",
                    "notes", "clinical_reasoning", "decision_rationale",
                ):
                    alias_val = decision.get(alias)
                    if isinstance(alias_val, str) and alias_val.strip():
                        decision["reasoning"] = alias_val.strip()
                        break
            if not str(decision.get("reasoning") or "").strip():
                _diag = extracted.get("diagnosis") or extracted.get("chief_complaint") or "unspecified diagnosis"
                _icd = coded.get("primary_diagnosis_code") or "N/A"
                _amt = float(extracted.get("total_amount_myr") or 0)
                _clinic = extracted.get("clinic_name") or "the clinic"
                decision["reasoning"] = (
                    f"Claim for {_diag} (ICD: {_icd}) at {_clinic}, billed RM {_amt:.2f}. "
                    "The adjudication engine processed this claim but did not return detailed reasoning from the AI model. "
                    "The claim has been routed for manual review to ensure proper evaluation against policy guidelines and fee schedules."
                )

            decision["denial_prediction"] = denial_predictor.predict_denial(full_claim_with_evidence)
            result["steps"]["denial_predictor"] = decision["denial_prediction"]
            db.insert_decision(claim_id, decision, run_id=processing_run_id, is_final=0)
            result["steps"]["adjudication"] = decision

            # Step 7: Fraud Detection
            logger.info(f"[{claim_id}] Step 7: Fraud Detection...")
            
            # MC Behavioral Analytics (Ultra Plan)
            import mc_analytics
            patient_mc_risk = mc_analytics.calculate_patient_mc_risk(extracted.get("patient_ic"))
            clinic_mc_risk = mc_analytics.calculate_clinic_mc_risk(extracted.get("clinic_id"))
            
            db.update_claim(claim_id, patient_mc_risk_score=patient_mc_risk, clinic_mc_risk_score=clinic_mc_risk)
            
            fraud = glm_client.detect_fraud_patterns(full_claim, claim_id=claim_id)
            graph_signal = fraud_graph.analyze_claim_network(extracted)
            fraud["graph_signal"] = graph_signal
            base_score = float(fraud.get("fraud_risk_score") or 0.0)
            
            # Boost fraud score if MC abuse is detected
            if patient_mc_risk > 0.5:
                base_score = max(base_score, 0.75)
                fraud.setdefault("flags", []).append({
                    "flag_type": "HR_ALERT_MC_ABUSE",
                    "description": "PRIORITY HR ALERT: Suspected Sick Leave Abuse (Weekend Extension Pattern)",
                    "severity": 0.8
                })
                pipeline_findings.append({
                    "severity": "WARN", # WARN so it doesn't block claim payment, just alerts
                    "source": "MC_BEHAVIORAL_ANALYTICS",
                    "detail": "🚨 PRIORITY HR ALERT: Suspected Sick Leave Abuse (Weekend Extension Pattern detected)."
                })
                
            adjusted = min(1.0, base_score * float(graph_signal.get("graph_risk_multiplier", 1.0)))
            fraud["fraud_risk_score"] = round(adjusted, 4)
            if adjusted >= 0.85:
                fraud["risk_level"] = "CRITICAL"
            elif adjusted >= 0.7:
                fraud["risk_level"] = "HIGH"
            db.insert_fraud_score(claim_id, fraud)
            db.update_claim(claim_id, fraud_flagged=1 if fraud.get("risk_level") in ["HIGH", "CRITICAL"] else 0)
            result["steps"]["fraud"] = fraud

            # Step 8: GP Advisory
            logger.info(f"[{claim_id}] Step 8: Generating GP Advisory...")
            advisory_input = dict(extracted)
            advisory_input["_validation_result"] = full_claim.get("_validation_result")
            advisory = glm_client.generate_gp_advisory(decision, advisory_input, claim_id=claim_id)
            db.insert_advisory(claim_id, advisory)
            result["steps"]["advisory"] = advisory

            # Generate EOB
            eob = eob_generator.generate_eob(claim_id, extracted, decision, eligibility)
            result["steps"]["eob"] = eob

            # Finalize — synthesize all findings into a final decision
            final_status = decision.get("decision", "APPROVED")
            fraud_level = fraud.get("risk_level", "LOW")
            fraud_rec = fraud.get("recommendation", "PROCEED")
            
            # Override based on synthesized findings
            critical_findings = [f for f in pipeline_findings if f["severity"] == "CRITICAL"]
            if critical_findings:
                # Determine if it's a hard denial or referral
                denial_findings = [f for f in critical_findings if f["source"] in ["ELIGIBILITY"]]
                fraud_findings = [f for f in critical_findings if f["source"] == "CROSS_REFERENCE"]
                scrub_findings = [f for f in critical_findings if f["source"] == "SCRUBBER"]
                validation_mismatch_findings = [f for f in critical_findings if f["source"] == "VALIDATION"]
                disposition_findings = [f for f in critical_findings if f["source"] == "DISPOSITION"]
                evidence_findings = [f for f in critical_findings if f["source"] == "MISSING_EVIDENCE"]
                
                if validation_mismatch_findings:
                    final_status = "UNDER_REVIEW"
                    decision["_validation_override"] = True
                    decision["_ai_decision"] = decision.get("decision")
                    decision["reasoning"] = (
                        "Data consistency mismatch detected between submitted claim and supporting evidence.\n\n"
                        + "\n".join([f"- {x['detail']}" for x in validation_mismatch_findings])
                        + "\n\nManual verification is required before adjudication can be finalized."
                    )
                elif fraud_findings or fraud_level in ("HIGH", "CRITICAL"):
                    final_status = "REFERRED"
                    decision["_fraud_override"] = True
                    decision["_ai_decision"] = decision.get("decision")
                    decision["_ai_confidence"] = decision.get("confidence")
                    original_reasoning = decision.get("reasoning", "")
                    fraud_detail = "\n\n".join([f["detail"] for f in fraud_findings])
                    decision["reasoning"] = (fraud_detail + "\n\n" + original_reasoning).strip()
                elif denial_findings:
                    final_status = "DENIED"
                    decision["reasoning"] = denial_findings[0]["detail"]
                    decision["denial_reason_code"] = denial_findings[0].get("carc", "16")
                elif scrub_findings:
                    final_status = "DENIED"
                    decision["reasoning"] = scrub_findings[0]["detail"]
                    decision["denial_reason_code"] = scrub_findings[0].get("carc", "16")
                elif disposition_findings or evidence_findings:
                    final_status = "UNDER_REVIEW"
                    synthesized = [x["detail"] for x in (disposition_findings + evidence_findings) if x.get("detail")]
                    if synthesized:
                        decision["reasoning"] = (
                            "Deterministic policy checks flagged this claim for manual review.\n\n"
                            + "\n".join([f"- {s}" for s in synthesized[:6]])
                        )
            
            if final_status == "APPROVED" and fraud_level in ("HIGH", "CRITICAL") and fraud_rec in ("INVESTIGATE", "BLOCK"):
                logger.warning(
                    f"[{claim_id}] Fraud gating triggered: {fraud_level}/{fraud_rec}. "
                    f"Overriding '{final_status}' → 'FRAUD_FLAG'."
                )
                final_status = "FRAUD_FLAG"
                decision["_fraud_override"] = True
                decision["_ai_decision"] = decision.get("_ai_decision") or decision.get("decision")
                decision["_ai_confidence"] = decision.get("_ai_confidence") or decision.get("confidence")
                original_reasoning = decision.get("reasoning", "")
                decision["reasoning"] = (
                    original_reasoning +
                    f"\n\n⚠️ FRAUD GATE: This claim was flagged as {fraud_level} risk "
                    f"(score: {fraud.get('fraud_risk_score', '?')}) with recommendation "
                    f"'{fraud_rec}'. Automatically referred for manual review."
                )
                
            # ENFORCE SAFETY FREEZE: All claims must undergo manual review.
            if final_status == "APPROVED":
                logger.warning(f"[{claim_id}] Safety Freeze: AI recommended APPROVED -> UNDER_REVIEW for human review.")
                final_status = "UNDER_REVIEW"
                decision["_freeze_override"] = True
                decision["_ai_decision"] = decision.get("_ai_decision") or "APPROVED"
                decision["_ai_confidence"] = decision.get("_ai_confidence") or decision.get("confidence")
                original_reasoning = decision.get("reasoning", "")
                decision["reasoning"] = (
                    original_reasoning + 
                    "\n\n⚠️ SAFETY FREEZE: This claim was marked for APPROVAL, but autonomous adjudication is currently disabled. Human sign-off is required."
                )

            # ENFORCE: No automatic denials. All DENIED claims go to UNDER_REVIEW for human sign-off.
            if final_status == "DENIED":
                logger.warning(f"[{claim_id}] Safety Gate: AI recommended DENIED -> UNDER_REVIEW for human review.")
                final_status = "UNDER_REVIEW"
                decision["_denial_override"] = True
                decision["_ai_decision"] = decision.get("_ai_decision") or "DENIED"
                decision["_ai_confidence"] = decision.get("_ai_confidence") or decision.get("confidence")
                original_reasoning = decision.get("reasoning", "")
                decision["reasoning"] = (
                    original_reasoning + 
                    "\n\n⚠️ SAFETY GATE: This claim was marked for DENIAL. "
                    "Per clinical safety rules, it requires human sign-off before final denial."
                )
                
            # Update the decision in DB if it was overridden
            if decision.get("_fraud_override") or decision.get("_denial_override") or decision.get("_freeze_override") or decision.get("_validation_override") or critical_findings:
                decision["decision"] = final_status
            # Final hardening: never persist an empty reasoning/confidence payload.
            if decision.get("confidence") is None:
                decision["confidence"] = decision.get("adjudication_confidence")
            if decision.get("confidence") is None:
                decision["confidence"] = 0.65
            if not str(decision.get("reasoning") or "").strip():
                reason_bits = []
                if critical_findings:
                    reason_bits.extend([f.get("detail", "") for f in critical_findings if f.get("detail")])
                if not reason_bits and disposition.get("rule_hits"):
                    reason_bits.extend([f"{h.get('rule_id')}: {h.get('reason')}" for h in disposition.get("rule_hits", []) if h.get("reason")])
                if not reason_bits:
                    dp = decision.get("denial_prediction") or {}
                    rf = dp.get("top_risk_factors") or []
                    if rf:
                        reason_bits.append(f"Top denial risk factors: {', '.join([str(x) for x in rf])}")
                if reason_bits:
                    decision["reasoning"] = "Manual review rationale:\n" + "\n".join([f"- {x}" for x in reason_bits[:6]])
                else:
                    decision["reasoning"] = "Manual review required based on adjudication and risk controls."
            db.insert_decision(claim_id, decision, run_id=processing_run_id, is_final=1)

            cycle_time = (time.time() - start_time) / 3600 # hours
            is_clean = (scrub["status"] != "FAIL") and bool(eligibility.get("eligible", False))
            db.update_claim(claim_id, status=final_status, lifecycle_stage=final_status,
                            clean_claim_flag=1 if is_clean else 0,
                            auto_adjudicated=1, cycle_time_hours=cycle_time, ar_days=1)
            result["final_status"] = final_status

        except glm_client.GLMServiceUnavailable as e:
            logger.error(f"[{claim_id}] GLM unavailable, forcing manual review: {e}")
            decision = {
                "decision": "REFERRED",
                "confidence": 0.0,
                "reasoning": str(e),
                "amount_approved_myr": 0.0,
                "amount_denied_myr": 0.0,
                "denial_reason_code": "16",
                "denial_reason_description": "Upstream adjudication service unavailable",
                "is_auto_adjudicated": 0,
                "model_version": "SERVICE_UNAVAILABLE",
            }
            db.insert_decision(claim_id, decision, run_id=processing_run_id, is_final=1)
            db.update_claim(
                claim_id,
                status="UNDER_REVIEW",
                lifecycle_stage="UNDER_REVIEW",
                clean_claim_flag=0,
                auto_adjudicated=0,
            )
            result["error"] = str(e)
            result["final_status"] = "UNDER_REVIEW"
        except Exception as e:
            logger.error(f"[{claim_id}] Pipeline failed: {e}")
            db.update_claim(claim_id, status="ERROR", lifecycle_stage="ERROR")
            result["error"] = str(e)
            result["final_status"] = "ERROR"

    finally:
        db.release_processing_lock(claim_id)

    return result
