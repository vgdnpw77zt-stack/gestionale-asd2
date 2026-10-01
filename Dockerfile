FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ASDPRO_RUNTIME_DIR=/data ASD_PRO_DATA_DIR=/data ASD_MAX_UPLOAD_MB=500
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr tesseract-ocr-ita poppler-utils libgl1 libglib2.0-0 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/bodymind
COPY requirements_runtime.txt /opt/bodymind/requirements_runtime.txt
RUN pip install --no-cache-dir -r /opt/bodymind/requirements_runtime.txt
COPY release_apply.py /opt/bodymind/release_apply.py
COPY release_autopilot_r3.py /opt/bodymind/release_autopilot_r3.py
COPY release_autopilot_r4.py /opt/bodymind/release_autopilot_r4.py
COPY release_autopilot_r5.py /opt/bodymind/release_autopilot_r5.py
COPY release_autopilot_r6.py /opt/bodymind/release_autopilot_r6.py
COPY release_autopilot_r8.py /opt/bodymind/release_autopilot_r8.py
COPY release_autopilot_r9.py /opt/bodymind/release_autopilot_r9.py
COPY release_document_ux_r10.py /opt/bodymind/release_document_ux_r10.py
COPY release_simplify_r11.py /opt/bodymind/release_simplify_r11.py
COPY release_mobile_r12.py /opt/bodymind/release_mobile_r12.py
COPY release_unified_r13.py /opt/bodymind/release_unified_r13.py
COPY release_document_repair_r14.py /opt/bodymind/release_document_repair_r14.py
COPY release_queue_integrity_r15.py /opt/bodymind/release_queue_integrity_r15.py
COPY release_unified_flags_r16.py /opt/bodymind/release_unified_flags_r16.py
COPY release_missing_docs_r17.py /opt/bodymind/release_missing_docs_r17.py
COPY release_inbound_filefix_r18.py /opt/bodymind/release_inbound_filefix_r18.py
COPY release_pending_dedupe_r19.py /opt/bodymind/release_pending_dedupe_r19.py
COPY release_dossier_missing_r23.py /opt/bodymind/release_dossier_missing_r23.py
COPY release_ocr_rematch_r20.py /opt/bodymind/release_ocr_rematch_r20.py
COPY release_force_pdf_ocr_r21.py /opt/bodymind/release_force_pdf_ocr_r21.py
COPY release_document_flow_r25.py /opt/bodymind/release_document_flow_r25.py
COPY release_document_preview_r26.py /opt/bodymind/release_document_preview_r26.py
COPY operator_bodymind_runtime_r29.py /opt/bodymind/operator_bodymind_runtime_r29.py
COPY operator_doc_semantic_core_r52.py /opt/bodymind/operator_doc_semantic_core_r52.py
COPY operator_doc_semantic_ai_r52.py /opt/bodymind/operator_doc_semantic_ai_r52.py
COPY release_operator_r29.py /opt/bodymind/release_operator_r29.py
COPY release_route_cleanup_r31.py /opt/bodymind/release_route_cleanup_r31.py
COPY release_operator_r30.py /opt/bodymind/release_operator_r30.py
COPY release_mu_tutela_r34.py /opt/bodymind/release_mu_tutela_r34.py
COPY release_mu_tutela_r36.py /opt/bodymind/release_mu_tutela_r36.py
COPY release_mu_tutela_r37.py /opt/bodymind/release_mu_tutela_r37.py
COPY release_document_coherence_r41.py /opt/bodymind/release_document_coherence_r41.py
COPY release_document_coherence_r42.py /opt/bodymind/release_document_coherence_r42.py
COPY release_operator_dedupe_rollback_r43.py /opt/bodymind/release_operator_dedupe_rollback_r43.py
COPY release_document_conflict_audit_r44.py /opt/bodymind/release_document_conflict_audit_r44.py
COPY release_cloud_native_r47.py /opt/bodymind/release_cloud_native_r47.py
COPY release_secretary_capability_audit_r48.py /opt/bodymind/release_secretary_capability_audit_r48.py
COPY release_operator_batch_r52.py /opt/bodymind/release_operator_batch_r52.py
COPY release_operator_upload_semantic_r52.py /opt/bodymind/release_operator_upload_semantic_r52.py
COPY release_operator_web_audio_r52.py /opt/bodymind/release_operator_web_audio_r52.py
COPY release_operator_autonomy_r55.py /opt/bodymind/release_operator_autonomy_r55.py
COPY release_operator_fast_dedupe_r56.py /opt/bodymind/release_operator_fast_dedupe_r56.py
COPY release_operator_dedupe_smoke_r56.py /opt/bodymind/release_operator_dedupe_smoke_r56.py
COPY release_operator_avatar_r57.py /opt/bodymind/release_operator_avatar_r57.py
COPY release_operator_voice_state_r59.py /opt/bodymind/release_operator_voice_state_r59.py
COPY release_operator_targeted_missing_r60.py /opt/bodymind/release_operator_targeted_missing_r60.py
COPY release_operator_intent_smoke_r57.py /opt/bodymind/release_operator_intent_smoke_r57.py
COPY release_operator_pending_reconcile_r55.py /opt/bodymind/release_operator_pending_reconcile_r55.py
COPY release_operator_pending_audit_r55e.py /opt/bodymind/release_operator_pending_audit_r55e.py
COPY release_operator_dinicola_r55f.py /opt/bodymind/release_operator_dinicola_r55f.py
COPY release_operator_read_smoke_r53.py /opt/bodymind/release_operator_read_smoke_r53.py
COPY release_operator_experience_r38.py /opt/bodymind/release_operator_experience_r38.py
COPY release_operator_qa_r32.py /opt/bodymind/release_operator_qa_r32.py
COPY release_operator_logic_qa_r34.py /opt/bodymind/release_operator_logic_qa_r34.py
COPY release_operator_logic_qa_r37.py /opt/bodymind/release_operator_logic_qa_r37.py
COPY release_operator_mobile_r33.py /opt/bodymind/release_operator_mobile_r33.py
COPY release_cleanup_r2.py /opt/bodymind/release_cleanup_r2.py
COPY runtime_timeline_inspect_r35.py /opt/bodymind/runtime_timeline_inspect_r35.py
COPY release_route_guard_r39.py /opt/bodymind/release_route_guard_r39.py
COPY build_preflight_r39.py /opt/bodymind/build_preflight_r39.py
COPY runtime_launcher.py /opt/bodymind/runtime_launcher.py
RUN python /opt/bodymind/build_preflight_r39.py
RUN mkdir -p /opt/bodymind-migration && cp /opt/bodymind/runtime_launcher.py /opt/bodymind-migration/migration_upload.py
EXPOSE 8080
CMD ["python","/opt/bodymind-migration/migration_upload.py"]
