// This file is generated. Do not edit manually.

export interface paths {
    "/api/v1/backups": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Backup */
        post: operations["create_backup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/backups/{backup_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Backup */
        post: operations["restore_backup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/ocr/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Document Ocr */
        post: operations["start_document_ocr"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/ocr/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Document Ocr Status */
        get: operations["get_document_ocr_status"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/glossaries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Glossaries */
        get: operations["list_glossaries"];
        put?: never;
        /** Create Glossary */
        post: operations["create_glossary"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/glossaries/{glossary_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Glossary */
        get: operations["get_glossary"];
        put?: never;
        post?: never;
        /** Delete Glossary */
        delete: operations["delete_glossary"];
        options?: never;
        head?: never;
        /** Update Glossary */
        patch: operations["update_glossary"];
        trace?: never;
    };
    "/api/v1/glossaries/{glossary_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activate Glossary */
        post: operations["activate_glossary"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/glossaries/{glossary_id}/deactivate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Deactivate Glossary */
        post: operations["deactivate_glossary"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/glossaries/{glossary_id}/terms": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Glossary Terms */
        get: operations["list_glossary_terms"];
        put?: never;
        /** Create Glossary Term */
        post: operations["create_glossary_term"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/glossary-terms/{term_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Glossary Term */
        get: operations["get_glossary_term"];
        put?: never;
        post?: never;
        /** Archive Glossary Term */
        delete: operations["archive_glossary_term"];
        options?: never;
        head?: never;
        /** Update Glossary Term */
        patch: operations["update_glossary_term"];
        trace?: never;
    };
    "/api/v1/glossary-terms/{term_id}/deactivate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Deactivate Glossary Term */
        post: operations["deactivate_glossary_term"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Jobs */
        get: operations["list_jobs"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job */
        get: operations["get_job"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/attempts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job Attempts */
        get: operations["get_job_attempts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Job */
        post: operations["cancel_job"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Job */
        post: operations["retry_job"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/cache-cleanup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cache Cleanup */
        post: operations["run_cache_cleanup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/database-integrity-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Database Integrity Check */
        post: operations["run_database_integrity_check"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/database-vacuum": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Database Vacuum */
        post: operations["run_database_vacuum"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/file-integrity-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** File Integrity Check */
        post: operations["run_file_integrity_check"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/orphan-file-scan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Orphan File Scan */
        post: operations["run_orphan_file_scan"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/maintenance/temp-cleanup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Temp Cleanup */
        post: operations["run_temp_cleanup"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Detected Local Models */
        get: operations["list_detected_local_models"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/ollama/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ollama Health */
        get: operations["get_ollama_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh Local Models */
        post: operations["refresh_local_models"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/{model_id}/benchmarks/quick": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Quick Benchmark */
        post: operations["start_quick_benchmark"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/models/{model_id}/select": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Select Local Model */
        post: operations["select_local_model"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pages/{page_id}/editor-view": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Page Editor View */
        get: operations["get_page_editor_view"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pages/{page_id}/ocr": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Page Ocr */
        get: operations["get_page_ocr"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects"];
        put?: never;
        /** Create Project */
        post: operations["create_project"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Project */
        patch: operations["update_project"];
        trace?: never;
    };
    "/api/v1/projects/{project_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Project */
        post: operations["archive_project"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/documents/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Document */
        post: operations["import_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/glossary-impact": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Analyze Project Glossary Impact */
        post: operations["analyze_glossary_impact"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/reconstruction-readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Reconstruction Readiness */
        get: operations["get_reconstruction_readiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/reconstruction/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Reconstruction */
        post: operations["cancel_reconstruction"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/reconstruction/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Reconstruction */
        post: operations["preview_reconstruction"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/reconstruction/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Reconstruction */
        post: operations["start_reconstruction"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/reconstruction/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Reconstruction Status */
        get: operations["get_reconstruction_status"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/review-queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Review Queue */
        get: operations["list_review_queue"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/translation-readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Translation Readiness */
        get: operations["get_translation_readiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/translation/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Translation */
        post: operations["cancel_translation"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/translation/retry-failed": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Failed Translation */
        post: operations["retry_failed_translation"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/translation/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Translation */
        post: operations["start_translation"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/translation/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Translation Status */
        get: operations["get_translation_status"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/unarchive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Unarchive Project */
        post: operations["unarchive_project"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/projects/{project_id}/warnings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Warnings */
        get: operations["list_warnings"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reconstruction/pages/{reconstruction_page_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Reconstruction Page */
        get: operations["get_reconstruction_page"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/reconstruction/pages/{reconstruction_page_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Reconstruction Page */
        post: operations["retry_reconstruction_page"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segment-revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Segment Revision */
        get: operations["get_segment_revision"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segments/bulk": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Bulk Segment Action */
        post: operations["bulk_segment_action"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Segment */
        post: operations["approve_segment"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/restore-revision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Segment Revision */
        post: operations["restore_segment_revision"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Segment Revisions */
        get: operations["list_segment_revisions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/source-resolution": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Resolve Segment Source */
        patch: operations["resolve_segment_source"];
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/translation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Edit Segment Translation */
        patch: operations["edit_segment_translation"];
        trace?: never;
    };
    "/api/v1/segments/{segment_id}/unapprove": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Unapprove Segment */
        post: operations["unapprove_segment"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Settings */
        get: operations["list_settings"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/settings/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate Settings */
        post: operations["validate_settings"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/settings/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Setting */
        get: operations["get_setting"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Setting */
        patch: operations["update_setting"];
        trace?: never;
    };
    "/api/v1/system/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get placeholder system health */
        get: operations["get_system_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/warnings/{warning_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Warning */
        get: operations["get_warning"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/warnings/{warning_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Warning */
        post: operations["accept_warning"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/warnings/{warning_id}/false-positive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Warning False Positive */
        post: operations["mark_warning_false_positive"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/warnings/{warning_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve Warning */
        post: operations["resolve_warning"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get API health */
        get: operations["get_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AnalysisJobData */
        AnalysisJobData: {
            /** Id */
            id: string;
            /**
             * Job Type
             * @default ANALYZE_DOCUMENT
             * @constant
             */
            job_type: "ANALYZE_DOCUMENT";
            status: components["schemas"]["JobStatus"];
        };
        /** ApproveSegmentRequest */
        ApproveSegmentRequest: {
            /** Expected Revision */
            expected_revision: number;
            /**
             * Lock After Approval
             * @default false
             */
            lock_after_approval: boolean;
        };
        /**
         * BackupType
         * @description Supported backup scopes.
         * @enum {string}
         */
        BackupType: "DATABASE_ONLY" | "METADATA" | "FULL_PROJECTS" | "FULL_APPLICATION" | "PRE_RESTORE";
        /** BenchmarkCaseResponse */
        BenchmarkCaseResponse: {
            /** Case Id */
            case_id: string;
            failure?: components["schemas"]["BenchmarkFailureResponse"] | null;
            /** Latency Seconds */
            latency_seconds: number | null;
            /** Placeholder Integrity */
            placeholder_integrity: boolean;
            /** Status */
            status: string;
            /** Structured Output Valid */
            structured_output_valid: boolean;
        };
        /** BenchmarkFailureResponse */
        BenchmarkFailureResponse: {
            /** Code */
            code: string;
            /**
             * Critical
             * @default false
             */
            critical: boolean;
            /** Message */
            message: string;
        };
        /**
         * BlockType
         * @enum {string}
         */
        BlockType: "DOCUMENT_TITLE" | "SUBTITLE" | "HEADING_1" | "HEADING_2" | "HEADING_3" | "HEADING_4" | "HEADING_5" | "HEADING_6" | "PARAGRAPH" | "BLOCKQUOTE" | "LIST" | "LIST_ITEM" | "TABLE" | "TABLE_ROW" | "TABLE_CELL" | "IMAGE" | "FIGURE" | "CAPTION" | "HEADER" | "FOOTER" | "PAGE_NUMBER" | "FOOTNOTE" | "ENDNOTE" | "CODE_BLOCK" | "INLINE_CODE_CONTAINER" | "FORMULA" | "EQUATION_LABEL" | "BIBLIOGRAPHY_ENTRY" | "INDEX_ENTRY" | "TABLE_OF_CONTENTS_ENTRY" | "SIDEBAR" | "CALLOUT" | "TEXTBOX" | "FORM_FIELD" | "SIGNATURE_FIELD" | "DECORATIVE_TEXT" | "UNKNOWN";
        /** Body_import_document */
        Body_import_document: {
            /** File */
            file: string;
            /**
             * Set As Active
             * @default true
             */
            set_as_active: boolean;
        };
        /** BulkSegmentActionData */
        BulkSegmentActionData: {
            /**
             * Action
             * @enum {string}
             */
            action: "approve" | "lock" | "retranslate";
            /** Failed */
            failed: number;
            /** Job Id */
            job_id?: string | null;
            /** Queued */
            queued: number;
            /** Results */
            results: components["schemas"]["BulkSegmentActionResult"][];
            /** Succeeded */
            succeeded: number;
        };
        /** BulkSegmentActionError */
        BulkSegmentActionError: {
            /** Code */
            code: string;
            /** Details */
            details?: {
                [key: string]: unknown;
            };
            /** Message */
            message: string;
        };
        /** BulkSegmentActionRequest */
        BulkSegmentActionRequest: {
            /**
             * Action
             * @enum {string}
             */
            action: "approve" | "lock" | "retranslate";
            /** Expected Revisions */
            expected_revisions?: {
                [key: string]: number;
            };
            /** Segment Ids */
            segment_ids?: string[] | null;
            /** Selected Ids */
            selected_ids?: string[] | null;
        };
        /** BulkSegmentActionResponse */
        BulkSegmentActionResponse: {
            data: components["schemas"]["BulkSegmentActionData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** BulkSegmentActionResult */
        BulkSegmentActionResult: {
            /** Current Revision */
            current_revision?: number | null;
            error?: components["schemas"]["BulkSegmentActionError"] | null;
            /** Segment Id */
            segment_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "FAILED" | "QUEUED" | "SUCCEEDED";
        };
        /** CancelJobRequest */
        CancelJobRequest: {
            /** Reason */
            reason: string;
        };
        /** CancelTranslationRequest */
        CancelTranslationRequest: {
            /** Reason */
            reason: string;
        };
        /** CollectionMeta */
        CollectionMeta: {
            pagination: components["schemas"]["OffsetPagination"];
            /** Request Id */
            request_id: string;
        };
        /** ComponentHealth */
        ComponentHealth: {
            /**
             * Status
             * @default UNAVAILABLE
             * @constant
             */
            status: "UNAVAILABLE";
        };
        /** CreateBackupData */
        CreateBackupData: {
            /** Backup Id */
            backup_id?: null;
            /** Job Id */
            job_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "QUEUED" | "RUNNING" | "RETRYING" | "CANCELLATION_REQUESTED" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "STALE";
        };
        /** CreateBackupRequest */
        CreateBackupRequest: {
            /**
             * Backup Type
             * @enum {string}
             */
            backup_type: "DATABASE_ONLY" | "METADATA" | "FULL_PROJECTS";
            /**
             * Include Exports
             * @default false
             */
            include_exports: boolean;
            /**
             * Include Intermediate Files
             * @default false
             */
            include_intermediate_files: boolean;
            /**
             * Include Original Files
             * @default false
             */
            include_original_files: boolean;
        };
        /** CreateBackupResponse */
        CreateBackupResponse: {
            data: components["schemas"]["CreateBackupData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** CreateGlossaryRequest */
        CreateGlossaryRequest: {
            /** Description */
            description?: string | null;
            /** Domain */
            domain?: string | null;
            /**
             * Is Default
             * @default false
             */
            is_default: boolean;
            /** Name */
            name: string;
            /** Project Id */
            project_id?: string | null;
            scope: components["schemas"]["GlossaryScope"];
            /** Source Language */
            source_language: string;
            /** Target Language */
            target_language: string;
        };
        /** CreateProjectRequest */
        CreateProjectRequest: {
            /** Description */
            description?: string | null;
            document_type: components["schemas"]["DocumentType"];
            /** Name */
            name: string;
            reconstruction_mode: components["schemas"]["ReconstructionMode"];
            /** Source Language */
            source_language: string;
            /** Target Language */
            target_language: string;
            translation_style: components["schemas"]["TranslationStyle"];
        };
        /** CreateTermRequest */
        CreateTermRequest: {
            /**
             * Capitalization Policy
             * @default MATCH_SENTENCE_POSITION
             */
            capitalization_policy: string;
            /**
             * Case Sensitive
             * @default false
             */
            case_sensitive: boolean;
            /**
             * Confidence
             * @default 1
             */
            confidence: number | null;
            /**
             * First Use Policy
             * @default NONE
             */
            first_use_policy: string;
            /**
             * Inflection Policy
             * @default USE_BASE_TERM
             */
            inflection_policy: string;
            /** @default PHRASE */
            match_mode: components["schemas"]["GlossaryMatchMode"];
            /** Notes */
            notes?: string | null;
            /**
             * Priority
             * @default 100
             */
            priority: number;
            rule_type: components["schemas"]["GlossaryRuleType"];
            scope: components["schemas"]["GlossaryScope"];
            /** Scope Reference Id */
            scope_reference_id?: string | null;
            /** Source Term */
            source_term: string;
            /** Target Term */
            target_term?: string | null;
            /**
             * Whole Word
             * @default true
             */
            whole_word: boolean;
        };
        /** CursorPagination */
        CursorPagination: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** DetectedLocalModel */
        DetectedLocalModel: {
            /** Disk Size Bytes */
            disk_size_bytes: number | null;
            /** Id */
            id: string;
            /** Is Installed */
            is_installed: boolean;
            /** Is Selected Translation */
            is_selected_translation: boolean;
            /** Is Selected Validation */
            is_selected_validation: boolean;
            license_status: components["schemas"]["ModelLicenseStatus"];
            /** Model Family */
            model_family: string | null;
            /** Ollama Model Name */
            ollama_model_name: string;
            /** Parameter Class */
            parameter_class: string | null;
            /** Quantization */
            quantization: string | null;
        };
        /** DetectedLocalModelResponse */
        DetectedLocalModelResponse: {
            data: components["schemas"]["DetectedLocalModel"];
            meta: components["schemas"]["ModelResponseMeta"];
        };
        /** DetectedLocalModelsResponse */
        DetectedLocalModelsResponse: {
            /** Data */
            data: components["schemas"]["DetectedLocalModel"][];
            meta: components["schemas"]["ModelResponseMeta"];
        };
        /** DocumentImportData */
        DocumentImportData: {
            document: components["schemas"]["ImportedDocumentData"];
            job: components["schemas"]["AnalysisJobData"];
        };
        /** DocumentImportResponse */
        DocumentImportResponse: {
            data: components["schemas"]["DocumentImportData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * DocumentStatus
         * @enum {string}
         */
        DocumentStatus: "CREATED" | "ANALYZED" | "EXTRACTED" | "OCR_PARTIAL" | "OCR_COMPLETE" | "STRUCTURED" | "TERMS_DETECTED" | "READY_FOR_TRANSLATION" | "TRANSLATING" | "TRANSLATED" | "PARTIALLY_TRANSLATED" | "REVIEWING" | "REVIEWED" | "RECONSTRUCTING" | "RECONSTRUCTED" | "QUALITY_CHECKED" | "READY_FOR_EXPORT" | "EXPORTED" | "FAILED" | "ARCHIVED";
        /**
         * DocumentType
         * @enum {string}
         */
        DocumentType: "ACADEMIC_PAPER" | "ACADEMIC_BOOK" | "TECHNICAL_BOOK" | "USER_MANUAL" | "BUSINESS_REPORT" | "LEGAL_DOCUMENT" | "FICTION_BOOK" | "NONFICTION_BOOK" | "PRESENTATION_EXPORT" | "BROCHURE" | "FORM" | "COMIC_OR_GRAPHIC_BOOK" | "GENERAL_DOCUMENT" | "UNKNOWN";
        /** EditSegmentTranslationRequest */
        EditSegmentTranslationRequest: {
            /** Expected Revision */
            expected_revision: number;
            /** Reason */
            reason?: string | null;
            /** Reviewed Translation */
            reviewed_translation: string;
        };
        /** ErrorBody */
        ErrorBody: {
            /** Code */
            code: string;
            details: components["schemas"]["ErrorDetails"];
            /** Message */
            message: string;
            /** Request Id */
            request_id: string;
        };
        ErrorDetails: {
            [key: string]: unknown;
        };
        /** ErrorResponse */
        ErrorResponse: {
            error: components["schemas"]["ErrorBody"];
        };
        /** GeometryResponse */
        GeometryResponse: {
            /** Coordinate System */
            coordinate_system: string;
            /** Height */
            height: number;
            /** Width */
            width: number;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /** GlossaryDataResponse */
        GlossaryDataResponse: {
            data: components["schemas"]["GlossaryResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** GlossaryImpactChangeRequest */
        GlossaryImpactChangeRequest: {
            proposed_rule_type: components["schemas"]["GlossaryRuleType"];
            /** Proposed Target Term */
            proposed_target_term?: string | null;
            /** Term Id */
            term_id: string;
        };
        /** GlossaryImpactConflictResponse */
        GlossaryImpactConflictResponse: {
            /** Blocking */
            blocking: boolean;
            /** Conflict Type */
            conflict_type: string;
            /** Explanation */
            explanation: string;
            /** Normalized Source Term */
            normalized_source_term: string;
            /** Resolution Status */
            resolution_status: string;
            /** Term Ids */
            term_ids: [
                string,
                string
            ];
            /** Winner Term Id */
            winner_term_id: string | null;
        };
        /** GlossaryImpactRequest */
        GlossaryImpactRequest: {
            /** Changes */
            changes: components["schemas"]["GlossaryImpactChangeRequest"][];
        };
        /** GlossaryImpactResponse */
        GlossaryImpactResponse: {
            data: components["schemas"]["GlossaryImpactResponseData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** GlossaryImpactResponseData */
        GlossaryImpactResponseData: {
            /** Affected Segments */
            affected_segments: number;
            /** Approved Segments */
            approved_segments: number;
            /** Conflicts */
            conflicts: components["schemas"]["GlossaryImpactConflictResponse"][];
            /** Locked Segments */
            locked_segments: number;
            /** Retranslation Recommended Segments */
            retranslation_recommended_segments: number;
            /** Safe Replacement Segments */
            safe_replacement_segments: number;
            /** Unreviewed Segments */
            unreviewed_segments: number;
        };
        /** GlossaryListResponse */
        GlossaryListResponse: {
            /** Data */
            data: components["schemas"]["GlossaryResponse"][];
            meta: components["schemas"]["CollectionMeta"];
        };
        /**
         * GlossaryMatchMode
         * @enum {string}
         */
        GlossaryMatchMode: "EXACT" | "PHRASE";
        /** GlossaryResponse */
        GlossaryResponse: {
            /** Created At */
            created_at: string;
            /** Description */
            description: string | null;
            /** Domain */
            domain: string | null;
            /** Id */
            id: string;
            /** Is Default */
            is_default: boolean;
            /** Name */
            name: string;
            /** Project Id */
            project_id: string | null;
            scope: components["schemas"]["GlossaryScope"];
            /** Source Language */
            source_language: string;
            status: components["schemas"]["GlossaryStatus"];
            /** Target Language */
            target_language: string;
            /** Term Count */
            term_count: number;
            /** Updated At */
            updated_at: string;
            /** Version */
            version: number;
        };
        /**
         * GlossaryRuleType
         * @enum {string}
         */
        GlossaryRuleType: "KEEP_ORIGINAL" | "TRANSLATE_AS" | "ORIGINAL_THEN_TRANSLATION" | "TRANSLATION_THEN_ORIGINAL" | "PRESERVE_ABBREVIATION" | "IGNORE";
        /**
         * GlossaryScope
         * @enum {string}
         */
        GlossaryScope: "SYSTEM" | "DOMAIN" | "USER" | "PROJECT" | "DOCUMENT" | "SECTION" | "PAGE" | "SEGMENT";
        /**
         * GlossaryStatus
         * @enum {string}
         */
        GlossaryStatus: "ACTIVE" | "INACTIVE";
        /**
         * GlossaryTermStatus
         * @enum {string}
         */
        GlossaryTermStatus: "ACTIVE" | "INACTIVE" | "ARCHIVED";
        /** HealthResponse */
        HealthResponse: {
            /**
             * Service
             * @default transloka-api
             * @constant
             */
            service: "transloka-api";
            /**
             * Status
             * @default ok
             * @constant
             */
            status: "ok";
            /**
             * Version
             * @default 0.1.0
             */
            version: string;
        };
        /** ImportedDocumentData */
        ImportedDocumentData: {
            /** Checksum Sha256 */
            checksum_sha256: string;
            /** Id */
            id: string;
            /** Original File Id */
            original_file_id: string;
            /** Original Filename */
            original_filename: string;
            /** Page Count */
            page_count: number;
            /** Project Id */
            project_id: string;
            /** Size Bytes */
            size_bytes: number;
            status: components["schemas"]["DocumentStatus"];
            /** Title */
            title: string | null;
        };
        /** JobAttemptErrorResponse */
        JobAttemptErrorResponse: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /** JobAttemptListResponse */
        JobAttemptListResponse: {
            /** Data */
            data: components["schemas"]["JobAttemptResponse"][];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** JobAttemptResponse */
        JobAttemptResponse: {
            /** Attempt Number */
            attempt_number: number;
            /** Completed At */
            completed_at: string | null;
            /** Duration Ms */
            duration_ms?: number | null;
            error: components["schemas"]["JobAttemptErrorResponse"] | null;
            /** Started At */
            started_at: string;
            status: components["schemas"]["JobAttemptStatus"];
        };
        /**
         * JobAttemptStatus
         * @enum {string}
         */
        JobAttemptStatus: "RUNNING" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "STALE";
        /** JobCollectionMeta */
        JobCollectionMeta: {
            pagination: components["schemas"]["CursorPagination"];
            /** Request Id */
            request_id: string;
        };
        /** JobDataResponse */
        JobDataResponse: {
            data: components["schemas"]["JobResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** JobErrorResponse */
        JobErrorResponse: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /** JobListResponse */
        JobListResponse: {
            /** Data */
            data: components["schemas"]["JobResponse"][];
            meta: components["schemas"]["JobCollectionMeta"];
        };
        /** JobResponse */
        JobResponse: {
            /** Completed At */
            completed_at: string | null;
            /** Created At */
            created_at: string;
            /** Current Stage */
            current_stage: string | null;
            /** Document Id */
            document_id: string | null;
            error: components["schemas"]["JobErrorResponse"] | null;
            /** Id */
            id: string;
            job_type: components["schemas"]["JobType"];
            /** Max Retries */
            max_retries: number;
            /** Progress */
            progress: number;
            /** Project Id */
            project_id: string | null;
            /** Retry Count */
            retry_count: number;
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["JobStatus"];
        };
        /**
         * JobStatus
         * @enum {string}
         */
        JobStatus: "CREATED" | "QUEUED" | "RUNNING" | "RETRYING" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLATION_REQUESTED" | "CANCELLED" | "STALE";
        /**
         * JobType
         * @enum {string}
         */
        JobType: "IMPORT_DOCUMENT" | "ANALYZE_DOCUMENT" | "OCR_DOCUMENT" | "DETECT_TERMS" | "TRANSLATE_DOCUMENT" | "RECONSTRUCT_DOCUMENT" | "EXPORT_DOCUMENT" | "BENCHMARK_MODEL" | "BACKUP_DATABASE" | "RESTORE_DATABASE" | "MAINTENANCE";
        /** MaintenanceData */
        MaintenanceData: {
            /** Candidates */
            candidates: string[];
            /** Checked Count */
            checked_count: number;
            /** Deleted */
            deleted: string[];
            /** Dry Run */
            dry_run: boolean;
            /** Healthy */
            healthy: boolean;
            /** Issue Count */
            issue_count: number;
            /** Issues */
            issues: string[];
            /** Job Id */
            job_id: string;
            operation: components["schemas"]["MaintenanceOperation"];
            /** Orphans */
            orphans: string[];
            /** Protected */
            protected: string[];
            /**
             * Status
             * @default COMPLETED
             * @constant
             */
            status: "COMPLETED";
        };
        /**
         * MaintenanceOperation
         * @enum {string}
         */
        MaintenanceOperation: "DATABASE_INTEGRITY_CHECK" | "FILE_INTEGRITY_CHECK" | "ORPHAN_FILE_SCAN" | "TEMP_CLEANUP" | "CACHE_CLEANUP" | "VACUUM";
        /** MaintenanceRequest */
        MaintenanceRequest: {
            /**
             * Dry Run
             * @default true
             */
            dry_run: boolean;
            /**
             * Older Than Days
             * @default 7
             */
            older_than_days: number;
        };
        /** MaintenanceResponse */
        MaintenanceResponse: {
            data: components["schemas"]["MaintenanceData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * ModelLicenseStatus
         * @enum {string}
         */
        ModelLicenseStatus: "APPROVED" | "APPROVED_FOR_PERSONAL_USE" | "REVIEW_REQUIRED" | "REJECTED" | "UNKNOWN";
        /** ModelResponseMeta */
        ModelResponseMeta: {
            /** Request Id */
            request_id: string;
            /** Warnings */
            warnings?: components["schemas"]["ModelWarning"][];
        };
        /**
         * ModelRole
         * @enum {string}
         */
        ModelRole: "TRANSLATION" | "VALIDATION";
        /** ModelWarning */
        ModelWarning: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Model Id */
            model_id: string;
        };
        /** OCRJobData */
        OCRJobData: {
            /** Job Id */
            job_id: string;
            status: components["schemas"]["JobStatus"];
        };
        /** OCRJobResponse */
        OCRJobResponse: {
            data: components["schemas"]["OCRJobData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** OCRPageData */
        OCRPageData: {
            /** Ocr Confidence */
            ocr_confidence?: number | null;
            /** Page Id */
            page_id: string;
            /** Raw Text */
            raw_text: string;
            /** Resolved Source Text */
            resolved_source_text: string;
            /** Segments */
            segments: components["schemas"]["OCRPageSegmentResponse"][];
        };
        /** OCRPageResponse */
        OCRPageResponse: {
            data: components["schemas"]["OCRPageData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** OCRPageSegmentResponse */
        OCRPageSegmentResponse: {
            /** Block Id */
            block_id: string;
            confidence: components["schemas"]["SegmentConfidenceResponse"];
            /** Current Revision */
            current_revision: number;
            /** Final Text */
            final_text: string | null;
            /** Global Order */
            global_order?: number | null;
            /** Id */
            id: string;
            /** Is Locked */
            is_locked: boolean;
            /** Machine Translation */
            machine_translation: string | null;
            /** Normalized Source Text */
            normalized_source_text: string;
            /** Raw Ocr Text */
            raw_ocr_text: string | null;
            /** Resolved Source Text */
            resolved_source_text: string;
            review_status: components["schemas"]["ReviewStatus"];
            /** Reviewed Translation */
            reviewed_translation: string | null;
            /** Section Id */
            section_id: string | null;
            /** Segment Order */
            segment_order: number;
            /** Source Language */
            source_language: string;
            /** Source Text */
            source_text: string;
            status: components["schemas"]["SegmentStatus"];
            /** Target Language */
            target_language: string;
            /** Warning Count */
            warning_count: number;
        };
        /** OCRStatusData */
        OCRStatusData: {
            /** Active Job Id */
            active_job_id: string | null;
            /** Completed Pages */
            completed_pages: number;
            /** Current Stage */
            current_stage: string | null;
            /** Failed Pages */
            failed_pages: number;
            /** Progress */
            progress: number;
            /** Selected Pages */
            selected_pages: number;
            /** Status */
            status: string;
        };
        /** OCRStatusResponse */
        OCRStatusResponse: {
            data: components["schemas"]["OCRStatusData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** OffsetPagination */
        OffsetPagination: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** OllamaHealthData */
        OllamaHealthData: {
            /** Base Url */
            base_url: string;
            status: components["schemas"]["ProviderHealthStatus"];
            /** Version */
            version: string;
        };
        /** OllamaHealthResponse */
        OllamaHealthResponse: {
            data: components["schemas"]["OllamaHealthData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** PageConfidenceResponse */
        PageConfidenceResponse: {
            /** Native Extraction */
            native_extraction?: number | null;
            /** Ocr */
            ocr?: number | null;
            /** Structure */
            structure?: number | null;
        };
        /** PageEditorBlockResponse */
        PageEditorBlockResponse: {
            block_type: components["schemas"]["BlockType"];
            /** Confidence */
            confidence?: number | null;
            /** Global Reading Order */
            global_reading_order?: number | null;
            /** Id */
            id: string;
            /** Normalized Source Text */
            normalized_source_text: string | null;
            /** Page Id */
            page_id: string;
            /** Page Reading Order */
            page_reading_order: number;
            /** Parent Block Id */
            parent_block_id: string | null;
            /** Section Id */
            section_id: string | null;
            semantic_role: components["schemas"]["SemanticRole"] | null;
            source_geometry: components["schemas"]["GeometryResponse"];
            /** Source Text */
            source_text: string | null;
            status: components["schemas"]["DocumentStatus"];
            target_geometry: components["schemas"]["GeometryResponse"] | null;
        };
        /** PageEditorPageResponse */
        PageEditorPageResponse: {
            /** Column Count */
            column_count: number;
            confidence: components["schemas"]["PageConfidenceResponse"];
            /** Document Id */
            document_id: string;
            /** Height Points */
            height_points: number;
            /** Id */
            id: string;
            /** Logical Page Number */
            logical_page_number: string | null;
            /** Page Classification */
            page_classification: string | null;
            page_type: components["schemas"]["PageType"];
            preview: components["schemas"]["PagePreviewResponse"];
            /** Reading Direction */
            reading_direction: string;
            /** Rotation Degrees */
            rotation_degrees: number;
            /** Source Page Number */
            source_page_number: number;
            status: components["schemas"]["DocumentStatus"];
            /** Width Points */
            width_points: number;
        };
        /** PageEditorSegmentResponse */
        PageEditorSegmentResponse: {
            /** Block Id */
            block_id: string;
            confidence: components["schemas"]["SegmentConfidenceResponse"];
            /** Current Revision */
            current_revision: number;
            /** Final Text */
            final_text: string | null;
            /** Global Order */
            global_order?: number | null;
            /** Id */
            id: string;
            /** Is Locked */
            is_locked: boolean;
            /** Machine Translation */
            machine_translation: string | null;
            /** Resolved Source Text */
            resolved_source_text: string;
            review_status: components["schemas"]["ReviewStatus"];
            /** Reviewed Translation */
            reviewed_translation: string | null;
            /** Section Id */
            section_id: string | null;
            /** Segment Order */
            segment_order: number;
            /** Source Language */
            source_language: string;
            /** Source Text */
            source_text: string;
            status: components["schemas"]["SegmentStatus"];
            /** Target Language */
            target_language: string;
            /** Warning Count */
            warning_count: number;
        };
        /** PageEditorViewData */
        PageEditorViewData: {
            /** Blocks */
            blocks: components["schemas"]["PageEditorBlockResponse"][];
            page: components["schemas"]["PageEditorPageResponse"];
            /** Segments */
            segments: components["schemas"]["PageEditorSegmentResponse"][];
            /** Warnings */
            warnings: components["schemas"]["PageEditorWarningResponse"][];
        };
        /** PageEditorViewResponse */
        PageEditorViewResponse: {
            data: components["schemas"]["PageEditorViewData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** PageEditorWarningResponse */
        PageEditorWarningResponse: {
            /** Created At */
            created_at: string;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Document Id */
            document_id: string;
            /** Id */
            id: string;
            /** Message */
            message: string;
            /** Page Id */
            page_id: string | null;
            /** Project Id */
            project_id: string;
            /** Resolved At */
            resolved_at: string | null;
            /** Segment Id */
            segment_id: string | null;
            /** Severity */
            severity: string;
            /** Status */
            status: string;
            /** Warning Type */
            warning_type: string;
        };
        /** PagePreviewResponse */
        PagePreviewResponse: {
            /** Render Url */
            render_url: string | null;
            /** Thumbnail Url */
            thumbnail_url: string | null;
        };
        /**
         * PageType
         * @enum {string}
         */
        PageType: "DIGITAL" | "SCANNED" | "HYBRID" | "IMAGE_ONLY" | "FORM" | "COVER" | "TABLE_OF_CONTENTS" | "INDEX" | "BIBLIOGRAPHY" | "BLANK" | "UNKNOWN";
        /** ProjectDataResponse */
        ProjectDataResponse: {
            data: components["schemas"]["ProjectResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** ProjectListResponse */
        ProjectListResponse: {
            /** Data */
            data: components["schemas"]["ProjectResponse"][];
            meta: components["schemas"]["CollectionMeta"];
        };
        /** ProjectResponse */
        ProjectResponse: {
            /** Active Document Id */
            active_document_id: string | null;
            /** Created At */
            created_at: string;
            /** Description */
            description: string | null;
            document_type: components["schemas"]["DocumentType"];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Progress */
            progress: number;
            reconstruction_mode: components["schemas"]["ReconstructionMode"];
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
            /** Source Language */
            source_language: string;
            status: components["schemas"]["ProjectStatus"];
            /** Target Language */
            target_language: string;
            translation_style: components["schemas"]["TranslationStyle"];
            /** Updated At */
            updated_at: string;
        };
        /**
         * ProjectStatus
         * @enum {string}
         */
        ProjectStatus: "CREATED" | "IMPORTING" | "ANALYZING" | "WAITING_FOR_SETTINGS" | "EXTRACTING" | "OCR_PROCESSING" | "TERMS_DETECTED" | "WAITING_FOR_GLOSSARY" | "TRANSLATING" | "READY_FOR_REVIEW" | "REVIEWING" | "RECONSTRUCTING" | "READY_FOR_EXPORT" | "COMPLETED" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "ARCHIVED" | "DELETION_QUEUED";
        /**
         * ProviderHealthStatus
         * @enum {string}
         */
        ProviderHealthStatus: "AVAILABLE" | "DEGRADED" | "UNAVAILABLE";
        /** QuickBenchmarkData */
        QuickBenchmarkData: {
            /** Average Latency Seconds */
            average_latency_seconds: number | null;
            /** Batch Sizes */
            batch_sizes: number[];
            /** Benchmark Id */
            benchmark_id: string;
            /** Benchmark Version */
            benchmark_version: string;
            /** Cases */
            cases: components["schemas"]["BenchmarkCaseResponse"][];
            /** Dataset Version */
            dataset_version: string;
            /** Failed Cases */
            failed_cases: number;
            failure?: components["schemas"]["BenchmarkFailureResponse"] | null;
            /** Model Id */
            model_id: string;
            /** Recommendation */
            recommendation: string;
            /** Status */
            status: string;
            /** Successful Cases */
            successful_cases: number;
            /** Temperature */
            temperature: number;
            /** Total Cases */
            total_cases: number;
        };
        /** QuickBenchmarkRequest */
        QuickBenchmarkRequest: {
            /** Batch Sizes */
            batch_sizes?: number[];
            /**
             * Dataset Version
             * @default translation_benchmark_en_id_0.1
             */
            dataset_version: string;
            /**
             * Temperature
             * @default 0.1
             */
            temperature: number;
        };
        /** QuickBenchmarkResponse */
        QuickBenchmarkResponse: {
            data: components["schemas"]["QuickBenchmarkData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * ReconstructionBlockStatus
         * @enum {string}
         */
        ReconstructionBlockStatus: "PENDING" | "PLACED" | "REFLOWED" | "PRESERVED" | "RENDERED_AS_IMAGE" | "OVERFLOW" | "COLLISION" | "NEEDS_REVIEW" | "FAILED";
        /** ReconstructionBlockingIssue */
        ReconstructionBlockingIssue: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /** ReconstructionJobData */
        ReconstructionJobData: {
            /** Job Id */
            job_id: string;
            status: components["schemas"]["JobStatus"];
        };
        /** ReconstructionJobResponse */
        ReconstructionJobResponse: {
            data: components["schemas"]["ReconstructionJobData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * ReconstructionMode
         * @enum {string}
         */
        ReconstructionMode: "OVERLAY" | "REFLOW" | "HYBRID";
        /** ReconstructionPageData */
        ReconstructionPageData: {
            /** Block Status */
            block_status: {
                [key: string]: components["schemas"]["ReconstructionBlockStatus"];
            };
            /** Id */
            id: string;
            /** Preview Endpoint */
            preview_endpoint: string | null;
            /** Source Page Id */
            source_page_id: string;
            status: components["schemas"]["ReconstructionStatus"];
            strategy: components["schemas"]["ReconstructionStrategy"];
            /** Target Page End */
            target_page_end: number;
            /** Target Page Mapping */
            target_page_mapping: {
                [key: string]: unknown;
            }[];
            /** Target Page Start */
            target_page_start: number;
            /** Warnings */
            warnings: components["schemas"]["ReconstructionBlockingIssue"][];
        };
        /** ReconstructionPageResponse */
        ReconstructionPageResponse: {
            data: components["schemas"]["ReconstructionPageData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** ReconstructionPreviewData */
        ReconstructionPreviewData: {
            mode: components["schemas"]["ReconstructionMode"];
            /** Page Id */
            page_id: string;
            /** Preview Id */
            preview_id: string;
            /** Status */
            status: string;
            /** Temporary */
            temporary: boolean;
            /** Warnings */
            warnings: components["schemas"]["ReconstructionBlockingIssue"][];
        };
        /** ReconstructionPreviewRequest */
        ReconstructionPreviewRequest: {
            mode: components["schemas"]["ReconstructionMode"];
            /** Page Id */
            page_id: string;
            settings?: components["schemas"]["ReconstructionSettings"];
        };
        /** ReconstructionPreviewResponse */
        ReconstructionPreviewResponse: {
            data: components["schemas"]["ReconstructionPreviewData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** ReconstructionReadinessData */
        ReconstructionReadinessData: {
            /** Available Modes */
            available_modes: components["schemas"]["ReconstructionMode"][];
            /** Blocking Issues */
            blocking_issues: components["schemas"]["ReconstructionBlockingIssue"][];
            /** Ready */
            ready: boolean;
            /** Warnings */
            warnings: components["schemas"]["ReconstructionWarning"][];
        };
        /** ReconstructionReadinessResponse */
        ReconstructionReadinessResponse: {
            data: components["schemas"]["ReconstructionReadinessData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** ReconstructionSettings */
        ReconstructionSettings: {
            /**
             * Allow Column Change
             * @default false
             */
            allow_column_change: boolean;
            /**
             * Allow Page Addition
             * @default true
             */
            allow_page_addition: boolean;
            /**
             * Block Export On Critical Errors
             * @default true
             */
            block_export_on_critical_errors: boolean;
            /**
             * Image Quality
             * @default STANDARD
             */
            image_quality: string;
            /**
             * Maximum Font Reduction Percent
             * @default 10
             */
            maximum_font_reduction_percent: number;
            /**
             * Minimum Body Font Pt
             * @default 8
             */
            minimum_body_font_pt: number;
            /**
             * Preserve Footers
             * @default true
             */
            preserve_footers: boolean;
            /**
             * Preserve Headers
             * @default true
             */
            preserve_headers: boolean;
            /**
             * Preserve Images
             * @default true
             */
            preserve_images: boolean;
            /**
             * Preserve Page Numbers
             * @default true
             */
            preserve_page_numbers: boolean;
            /**
             * Preserve Page Size
             * @default true
             */
            preserve_page_size: boolean;
            /**
             * Table Complexity Fallback
             * @default PRESERVE_AS_IMAGE
             */
            table_complexity_fallback: string;
            /**
             * Translate Captions
             * @default true
             */
            translate_captions: boolean;
        } & {
            [key: string]: unknown;
        };
        /**
         * ReconstructionStatus
         * @enum {string}
         */
        ReconstructionStatus: "NOT_STARTED" | "PREPARING" | "MEASURING" | "LAYING_OUT" | "RENDERING" | "VALIDATING" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED";
        /** ReconstructionStatusData */
        ReconstructionStatusData: {
            /** Active Job Id */
            active_job_id: string | null;
            /** Completed Pages */
            completed_pages: number;
            /** Critical Warning Count */
            critical_warning_count: number;
            /** Generated Target Pages */
            generated_target_pages: number;
            /** Progress */
            progress: number;
            /** Status */
            status: string;
            /** Total Source Pages */
            total_source_pages: number;
            /** Warning Count */
            warning_count: number;
        };
        /** ReconstructionStatusResponse */
        ReconstructionStatusResponse: {
            data: components["schemas"]["ReconstructionStatusData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * ReconstructionStrategy
         * @enum {string}
         */
        ReconstructionStrategy: "PRESERVE" | "OVERLAY" | "REFLOW" | "RECONSTRUCT" | "RENDER_AS_IMAGE" | "MANUAL_REVIEW";
        /** ReconstructionWarning */
        ReconstructionWarning: {
            /** Code */
            code: string;
            /** Count */
            count: number;
        };
        /** ResolveWarningRequest */
        ResolveWarningRequest: {
            /** Resolution Note */
            resolution_note?: string | null;
            /**
             * Resolution Type
             * @constant
             */
            resolution_type: "USER_FIXED";
        };
        /** ResponseMeta */
        ResponseMeta: {
            /** Request Id */
            request_id: string;
        };
        /** RestoreData */
        RestoreData: {
            /** Backup Id */
            backup_id: string;
            backup_type: components["schemas"]["BackupType"];
            /** Job Id */
            job_id: string;
            /** Pre Restore Backup Id */
            pre_restore_backup_id: string;
            /**
             * Status
             * @default COMPLETED
             * @constant
             */
            status: "COMPLETED";
        };
        /** RestoreRequest */
        RestoreRequest: {
            /**
             * Confirmation
             * @constant
             */
            confirmation: "RESTORE";
            /**
             * Create Pre Restore Backup
             * @default true
             * @constant
             */
            create_pre_restore_backup: true;
            /**
             * Restore Files
             * @default true
             */
            restore_files: boolean;
        };
        /** RestoreResponse */
        RestoreResponse: {
            data: components["schemas"]["RestoreData"];
        };
        /** RestoreRevisionRequest */
        RestoreRevisionRequest: {
            /** Expected Revision */
            expected_revision: number;
            /** Revision Id */
            revision_id: string;
        };
        /** RestoreRevisionResponse */
        RestoreRevisionResponse: {
            data: components["schemas"]["PageEditorSegmentResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** RetryJobRequest */
        RetryJobRequest: {
            /** Retry Failed Items Only */
            retry_failed_items_only: boolean;
        };
        /** RetryReconstructionPageRequest */
        RetryReconstructionPageRequest: {
            fallback_mode: components["schemas"]["ReconstructionMode"];
            /** Override Settings */
            override_settings?: {
                [key: string]: unknown;
            };
        };
        /** RetryTranslationRequest */
        RetryTranslationRequest: {
            /**
             * Use Selected Model
             * @default true
             */
            use_selected_model: boolean;
            /**
             * Use Smaller Batch
             * @default true
             */
            use_smaller_batch: boolean;
        };
        /** ReviewQueueItem */
        ReviewQueueItem: {
            segment: components["schemas"]["PageEditorSegmentResponse"];
            source_context: components["schemas"]["ReviewQueueSourceContext"];
            /** Warnings */
            warnings?: components["schemas"]["PageEditorWarningResponse"][];
        };
        /** ReviewQueueMeta */
        ReviewQueueMeta: {
            pagination: components["schemas"]["ReviewQueuePagination"];
            /** Request Id */
            request_id: string;
        };
        /** ReviewQueuePagination */
        ReviewQueuePagination: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ReviewQueueResponse */
        ReviewQueueResponse: {
            /** Data */
            data: components["schemas"]["ReviewQueueItem"][];
            meta: components["schemas"]["ReviewQueueMeta"];
        };
        /** ReviewQueueSourceContext */
        ReviewQueueSourceContext: {
            /** Heading */
            heading: string | null;
            /** Next Segment */
            next_segment: string | null;
            /** Previous Segment */
            previous_segment: string | null;
        };
        /**
         * ReviewStatus
         * @enum {string}
         */
        ReviewStatus: "NOT_REVIEWED" | "REVIEW_REQUIRED" | "IN_REVIEW" | "EDITED" | "APPROVED" | "REJECTED";
        /** RevisionCollectionMeta */
        RevisionCollectionMeta: {
            pagination: components["schemas"]["CursorPagination"];
            /** Request Id */
            request_id: string;
        };
        /** SegmentConfidenceResponse */
        SegmentConfidenceResponse: {
            /** Overall */
            overall?: number | null;
        };
        /** SegmentDataResponse */
        SegmentDataResponse: {
            data: components["schemas"]["PageEditorSegmentResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** SegmentRevisionDataResponse */
        SegmentRevisionDataResponse: {
            data: components["schemas"]["SegmentRevisionResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** SegmentRevisionListResponse */
        SegmentRevisionListResponse: {
            /** Data */
            data: components["schemas"]["SegmentRevisionResponse"][];
            meta: components["schemas"]["RevisionCollectionMeta"];
        };
        /** SegmentRevisionResponse */
        SegmentRevisionResponse: {
            /** Created At */
            created_at: string;
            /** Id */
            id: string;
            /** Metadata Json */
            metadata_json: string | null;
            /** New Text */
            new_text: string;
            /** Previous Text */
            previous_text: string | null;
            /** Reason */
            reason: string | null;
            /** Revision Number */
            revision_number: number;
            revision_type: components["schemas"]["SegmentRevisionType"];
            /** Segment Id */
            segment_id: string;
            /** Source Translation Id */
            source_translation_id: string | null;
        };
        /**
         * SegmentRevisionType
         * @enum {string}
         */
        SegmentRevisionType: "MACHINE_TRANSLATION" | "AUTOMATIC_RETRY" | "GLOSSARY_REAPPLICATION" | "USER_EDIT" | "APPROVE" | "UNAPPROVE" | "LOCK" | "UNLOCK" | "RESTORE_VERSION";
        /**
         * SegmentStatus
         * @enum {string}
         */
        SegmentStatus: "CREATED" | "EXTRACTED" | "OCR_REQUIRED" | "OCR_COMPLETED" | "NORMALIZED" | "TERMS_DETECTED" | "PROTECTED" | "READY_FOR_TRANSLATION" | "TRANSLATING" | "MACHINE_TRANSLATED" | "TRANSLATION_FAILED" | "NEEDS_REVIEW" | "USER_EDITED" | "APPROVED" | "LOCKED" | "IGNORED" | "NOT_TRANSLATABLE";
        /** SelectModelRequest */
        SelectModelRequest: {
            role: components["schemas"]["ModelRole"];
        };
        /**
         * SemanticRole
         * @enum {string}
         */
        SemanticRole: "TITLE" | "CHAPTER_TITLE" | "SECTION_TITLE" | "BODY_TEXT" | "DEFINITION" | "EXAMPLE" | "WARNING" | "NOTE" | "TIP" | "QUOTE" | "CAPTION" | "REFERENCE" | "CODE" | "FORMULA" | "NAVIGATION" | "DECORATION";
        /**
         * SettingCategory
         * @enum {string}
         */
        SettingCategory: "GENERAL" | "STORAGE" | "TRANSLATION" | "OCR" | "RECONSTRUCTION" | "BACKUP" | "ADVANCED";
        /** SettingDataResponse */
        SettingDataResponse: {
            data: components["schemas"]["SettingResponse"];
        };
        /** SettingResponse */
        SettingResponse: {
            category: components["schemas"]["SettingCategory"];
            /** Key */
            key: string;
            /** Updated At */
            updated_at: string;
            /** Value */
            value: unknown;
        };
        /** SettingsListResponse */
        SettingsListResponse: {
            /** Data */
            data: components["schemas"]["SettingResponse"][];
        };
        /** SettingsValidationData */
        SettingsValidationData: {
            /** Valid */
            valid: boolean;
        };
        /** SettingsValidationResponse */
        SettingsValidationResponse: {
            data: components["schemas"]["SettingsValidationData"];
        };
        /** SourceResolutionRequest */
        SourceResolutionRequest: {
            /** Expected Revision */
            expected_revision: number;
            /** Reason */
            reason?: string | null;
            /**
             * Resolution Source
             * @default MANUAL
             * @enum {string}
             */
            resolution_source: "AUTO" | "AUTOMATIC" | "MANUAL" | "NATIVE" | "OCR";
            /** Resolved Source Text */
            resolved_source_text: string;
        };
        /** SourceResolutionResponse */
        SourceResolutionResponse: {
            data: components["schemas"]["SourceResolutionSegmentResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** SourceResolutionSegmentResponse */
        SourceResolutionSegmentResponse: {
            /** Block Id */
            block_id: string;
            confidence: components["schemas"]["SegmentConfidenceResponse"];
            /** Current Revision */
            current_revision: number;
            /** Final Text */
            final_text: string | null;
            /** Global Order */
            global_order?: number | null;
            /** Id */
            id: string;
            /** Is Locked */
            is_locked: boolean;
            /** Machine Translation */
            machine_translation: string | null;
            /** Normalized Source Text */
            normalized_source_text: string;
            /** Raw Ocr Text */
            raw_ocr_text: string | null;
            /** Resolution Source */
            resolution_source: string;
            /** Resolved Source Text */
            resolved_source_text: string;
            review_status: components["schemas"]["ReviewStatus"];
            /** Reviewed Translation */
            reviewed_translation: string | null;
            /** Section Id */
            section_id: string | null;
            /** Segment Order */
            segment_order: number;
            /** Source Language */
            source_language: string;
            /** Source Text */
            source_text: string;
            status: components["schemas"]["SegmentStatus"];
            /** Target Language */
            target_language: string;
            /** Warning Count */
            warning_count: number;
        };
        /** StartOCRRequest */
        StartOCRRequest: {
            /**
             * Detect Formulas
             * @default true
             */
            detect_formulas: boolean;
            /**
             * Detect Tables
             * @default true
             */
            detect_tables: boolean;
            /**
             * Language
             * @default en
             */
            language: string;
            /**
             * Mode
             * @default AUTO
             * @enum {string}
             */
            mode: "AUTO" | "FORCE";
            /** Page Ids */
            page_ids?: string[] | null;
        };
        /** StartReconstructionRequest */
        StartReconstructionRequest: {
            mode: components["schemas"]["ReconstructionMode"];
            /** Page Ids */
            page_ids?: string[] | null;
            settings?: components["schemas"]["ReconstructionSettings"];
        };
        /** StartTranslationRequest */
        StartTranslationRequest: {
            /**
             * Batch Size
             * @default 5
             */
            batch_size: number;
            /**
             * Context Mode
             * @default STANDARD
             * @enum {string}
             */
            context_mode: "NONE" | "STANDARD" | "EXTENDED";
            /** Model Id */
            model_id: string;
            /** Page Ids */
            page_ids?: string[] | null;
            /**
             * Retranslate Existing
             * @default false
             */
            retranslate_existing: boolean;
            /**
             * Run Semantic Validation
             * @default false
             */
            run_semantic_validation: boolean;
            /**
             * Scope
             * @default FULL_DOCUMENT
             * @enum {string}
             */
            scope: "FULL_DOCUMENT" | "UNTRANSLATED_ONLY" | "UNREVIEWED_ONLY" | "SECTION" | "PAGE" | "SELECTED_SEGMENTS";
            /** Section Ids */
            section_ids?: string[] | null;
            /** Segment Ids */
            segment_ids?: string[] | null;
            /**
             * Skip Locked Segments
             * @default true
             */
            skip_locked_segments: boolean;
            translation_style?: components["schemas"]["TranslationStyle"] | null;
        };
        /** SystemComponents */
        SystemComponents: {
            database?: components["schemas"]["ComponentHealth"];
            filesystem?: components["schemas"]["ComponentHealth"];
            ocr?: components["schemas"]["ComponentHealth"];
            ollama?: components["schemas"]["ComponentHealth"];
            worker?: components["schemas"]["ComponentHealth"];
        };
        /** SystemHealthData */
        SystemHealthData: {
            components?: components["schemas"]["SystemComponents"];
            /**
             * Status
             * @default DEGRADED
             * @constant
             */
            status: "DEGRADED";
        };
        /** SystemHealthResponse */
        SystemHealthResponse: {
            data?: components["schemas"]["SystemHealthData"];
        };
        /** TermDataResponse */
        TermDataResponse: {
            data: components["schemas"]["TermResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** TermListResponse */
        TermListResponse: {
            /** Data */
            data: components["schemas"]["TermResponse"][];
            meta: components["schemas"]["CollectionMeta"];
        };
        /** TermResponse */
        TermResponse: {
            /** Capitalization Policy */
            capitalization_policy: string;
            /** Case Sensitive */
            case_sensitive: boolean;
            /** Confidence */
            confidence: number | null;
            /** Created At */
            created_at: string;
            /** Current Revision */
            current_revision: number;
            /** First Use Policy */
            first_use_policy: string;
            /** Glossary Id */
            glossary_id: string;
            /** Id */
            id: string;
            /** Inflection Policy */
            inflection_policy: string;
            match_mode: components["schemas"]["GlossaryMatchMode"];
            /** Normalized Source Term */
            normalized_source_term: string;
            /** Notes */
            notes: string | null;
            /** Occurrence Count */
            occurrence_count: number;
            /** Priority */
            priority: number;
            rule_type: components["schemas"]["GlossaryRuleType"];
            scope: components["schemas"]["GlossaryScope"];
            /** Scope Reference Id */
            scope_reference_id: string | null;
            /** Source Term */
            source_term: string;
            status: components["schemas"]["GlossaryTermStatus"];
            /** Target Term */
            target_term: string | null;
            /** Term Source */
            term_source: string;
            /** Updated At */
            updated_at: string;
            /** Whole Word */
            whole_word: boolean;
        };
        /** TranslationBlockingIssue */
        TranslationBlockingIssue: {
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /** TranslationJobData */
        TranslationJobData: {
            /** Job Id */
            job_id: string;
            status: components["schemas"]["JobStatus"];
        };
        /** TranslationJobResponse */
        TranslationJobResponse: {
            data: components["schemas"]["TranslationJobData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** TranslationReadinessData */
        TranslationReadinessData: {
            /** Blocking Issues */
            blocking_issues: components["schemas"]["TranslationBlockingIssue"][];
            /** Estimated Batches */
            estimated_batches: number;
            /** Ready */
            ready: boolean;
            /** Segment Count */
            segment_count: number;
            /** Warnings */
            warnings: components["schemas"]["TranslationReadinessWarning"][];
        };
        /** TranslationReadinessResponse */
        TranslationReadinessResponse: {
            data: components["schemas"]["TranslationReadinessData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** TranslationReadinessWarning */
        TranslationReadinessWarning: {
            /** Code */
            code: string;
            /** Count */
            count: number;
        };
        /** TranslationStatusData */
        TranslationStatusData: {
            /** Active Job Id */
            active_job_id: string | null;
            /** Completed Segments */
            completed_segments: number;
            /** Current Batch */
            current_batch: number;
            /** Failed Segments */
            failed_segments: number;
            /** Progress */
            progress: number;
            /** Review Required Segments */
            review_required_segments: number;
            /** Status */
            status: string;
            /** Total Batches */
            total_batches: number;
            /** Total Segments */
            total_segments: number;
        };
        /** TranslationStatusResponse */
        TranslationStatusResponse: {
            data: components["schemas"]["TranslationStatusData"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /**
         * TranslationStyle
         * @enum {string}
         */
        TranslationStyle: "LITERAL" | "PROFESSIONAL" | "ACADEMIC" | "NATURAL";
        /** UnapproveSegmentRequest */
        UnapproveSegmentRequest: {
            /** Expected Revision */
            expected_revision: number;
            /** Reason */
            reason?: string | null;
        };
        /** UpdateGlossaryRequest */
        UpdateGlossaryRequest: {
            /** Description */
            description?: string | null;
            /** Expected Version */
            expected_version: number;
            /** Name */
            name?: string | null;
        };
        /** UpdateProjectRequest */
        UpdateProjectRequest: {
            /** Name */
            name?: string | null;
            reconstruction_mode?: components["schemas"]["ReconstructionMode"] | null;
            translation_style?: components["schemas"]["TranslationStyle"] | null;
        };
        /** UpdateSettingRequest */
        UpdateSettingRequest: {
            /** Value */
            value: unknown;
        };
        /** UpdateTermRequest */
        UpdateTermRequest: {
            /** Capitalization Policy */
            capitalization_policy?: string | null;
            /** Case Sensitive */
            case_sensitive?: boolean | null;
            /** Confidence */
            confidence?: number | null;
            /** Expected Revision */
            expected_revision: number;
            /** First Use Policy */
            first_use_policy?: string | null;
            /** Inflection Policy */
            inflection_policy?: string | null;
            match_mode?: components["schemas"]["GlossaryMatchMode"] | null;
            /** Notes */
            notes?: string | null;
            /** Priority */
            priority?: number | null;
            /** Reason */
            reason?: string | null;
            rule_type?: components["schemas"]["GlossaryRuleType"] | null;
            scope?: components["schemas"]["GlossaryScope"] | null;
            /** Scope Reference Id */
            scope_reference_id?: string | null;
            /** Source Term */
            source_term?: string | null;
            /** Target Term */
            target_term?: string | null;
            /** Whole Word */
            whole_word?: boolean | null;
        };
        /** ValidateSettingsRequest */
        ValidateSettingsRequest: {
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
        };
        /** WarningDataResponse */
        WarningDataResponse: {
            data: components["schemas"]["WarningResponse"];
            meta: components["schemas"]["ResponseMeta"];
        };
        /** WarningListMeta */
        WarningListMeta: {
            pagination: components["schemas"]["WarningPagination"];
            /** Request Id */
            request_id: string;
        };
        /** WarningListResponse */
        WarningListResponse: {
            /** Data */
            data: components["schemas"]["WarningResponse"][];
            meta: components["schemas"]["WarningListMeta"];
        };
        /** WarningNoteRequest */
        WarningNoteRequest: {
            /** Resolution Note */
            resolution_note?: string | null;
        };
        /** WarningPagination */
        WarningPagination: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * WarningResolutionType
         * @enum {string}
         */
        WarningResolutionType: "AUTO_FIXED" | "USER_FIXED" | "USER_ACCEPTED" | "FALSE_POSITIVE" | "IGNORED_BY_POLICY" | "REQUIRES_REPROCESSING";
        /** WarningResponse */
        WarningResponse: {
            /** Created At */
            created_at: string;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Document Id */
            document_id: string | null;
            /** Id */
            id: string;
            /** Message */
            message: string;
            /** Page Id */
            page_id: string | null;
            /** Project Id */
            project_id: string;
            /** Resolution Note */
            resolution_note: string | null;
            resolution_type: components["schemas"]["WarningResolutionType"] | null;
            /** Resolved At */
            resolved_at: string | null;
            /** Segment Id */
            segment_id: string | null;
            severity: components["schemas"]["WarningSeverity"];
            status: components["schemas"]["WarningStatus"];
            warning_type: components["schemas"]["WarningType"];
        };
        /**
         * WarningSeverity
         * @enum {string}
         */
        WarningSeverity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
        /**
         * WarningStatus
         * @enum {string}
         */
        WarningStatus: "OPEN" | "RESOLVED" | "ACCEPTED" | "FALSE_POSITIVE" | "IGNORED_BY_POLICY";
        /**
         * WarningType
         * @enum {string}
         */
        WarningType: "TEXT_EXTRACTION_FAILED" | "READING_ORDER_UNCERTAIN" | "UNKNOWN_CHARACTER" | "FONT_MAPPING_FAILED" | "LOW_OCR_CONFIDENCE" | "OCR_TEXT_CONFLICT" | "UNREADABLE_REGION" | "ROTATION_UNCERTAIN" | "TRANSLATION_FAILED" | "LOW_TRANSLATION_CONFIDENCE" | "UNTRANSLATED_TEXT" | "TARGET_LANGUAGE_MISMATCH" | "POSSIBLE_HALLUCINATION" | "SOURCE_MEANING_DRIFT" | "GLOSSARY_NOT_APPLIED" | "TERM_INCONSISTENT" | "PLACEHOLDER_MISSING" | "PLACEHOLDER_DUPLICATED" | "CASE_MISMATCH" | "NUMBER_CHANGED" | "DATE_CHANGED" | "UNIT_CHANGED" | "URL_CHANGED" | "CITATION_CHANGED" | "CODE_CHANGED" | "TEXT_OVERFLOW" | "TEXT_CLIPPED" | "TEXT_OVERLAP" | "MISSING_TRANSLATED_SEGMENT" | "PLACEHOLDER_RESTORATION_FAILED" | "OUTPUT_PDF_CORRUPTED" | "ORIGINAL_FILE_CHECKSUM_MISMATCH" | "PATH_TRAVERSAL_DETECTED" | "TABLE_STRUCTURE_CORRUPTED_CRITICAL" | "CRITICAL_TEXT_CLIPPING" | "CRITICAL_LAYOUT_COLLISION" | "IMAGE_OVERLAP" | "MISSING_IMAGE" | "TABLE_OVERFLOW" | "FONT_TOO_SMALL" | "PAGE_ADDED" | "LAYOUT_SHIFT" | "HEADING_LEVEL_CHANGED" | "LIST_NUMBERING_CHANGED" | "TABLE_STRUCTURE_CHANGED" | "FOOTNOTE_LINK_BROKEN" | "READING_ORDER_CHANGED";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    create_backup: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateBackupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateBackupResponse"];
                };
            };
            /** @description The backup was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore conflicts with existing state or maintenance. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore request or archive is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The application is in maintenance mode. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    restore_backup: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                backup_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestoreRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RestoreResponse"];
                };
            };
            /** @description The backup was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore conflicts with existing state or maintenance. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore request or archive is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The restore could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The application is in maintenance mode. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_document_ocr: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartOCRRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OCRJobResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The OCR page or segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The OCR queue is not configured. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_document_ocr_status: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OCRStatusResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The OCR page or segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_glossaries: {
        parameters: {
            query?: {
                project_id?: string | null;
                scope?: components["schemas"]["GlossaryScope"] | null;
                status?: components["schemas"]["GlossaryStatus"] | null;
                search?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateGlossaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateGlossaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    activate_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    deactivate_glossary: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_glossary_terms: {
        parameters: {
            query?: {
                search?: string | null;
                rule_type?: components["schemas"]["GlossaryRuleType"] | null;
                status?: components["schemas"]["GlossaryTermStatus"] | null;
                source?: string | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_glossary_term: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                glossary_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTermRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_glossary_term: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                term_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    archive_glossary_term: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                term_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_glossary_term: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                term_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateTermRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    deactivate_glossary_term: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                term_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TermDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_jobs: {
        parameters: {
            query?: {
                project_id?: string | null;
                document_id?: string | null;
                job_type?: components["schemas"]["JobType"] | null;
                status?: components["schemas"]["JobStatus"] | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_job: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_job_attempts: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAttemptListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    cancel_job: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelJobRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job state does not allow cancellation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    retry_job: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryJobRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The job state, retry limit, or idempotency key prevents retry. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_cache_cleanup: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["MaintenanceRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_database_integrity_check: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_database_vacuum: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["MaintenanceRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_file_integrity_check: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_orphan_file_scan: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    run_temp_cleanup: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["MaintenanceRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MaintenanceResponse"];
                };
            };
            /** @description Maintenance conflicts with an active job. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The maintenance request is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Maintenance could not be completed safely. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_detected_local_models: {
        parameters: {
            query?: {
                installed?: boolean | null;
                selected_for_translation?: boolean | null;
                selected_for_validation?: boolean | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetectedLocalModelsResponse"];
                };
            };
            /** @description A remote Ollama endpoint was blocked. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model is unavailable or cannot be selected. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local Ollama service is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_ollama_health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OllamaHealthResponse"];
                };
            };
            /** @description A remote Ollama endpoint was blocked. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model is unavailable or cannot be selected. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local Ollama service is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    refresh_local_models: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetectedLocalModelsResponse"];
                };
            };
            /** @description A remote Ollama endpoint was blocked. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model is unavailable or cannot be selected. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local Ollama service is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_quick_benchmark: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["QuickBenchmarkRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuickBenchmarkResponse"];
                };
            };
            /** @description The request was rejected by local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The benchmark request conflicts with an existing run. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model provider is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    select_local_model: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SelectModelRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DetectedLocalModelResponse"];
                };
            };
            /** @description A remote Ollama endpoint was blocked. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local model is unavailable or cannot be selected. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The local Ollama service is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_page_editor_view: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PageEditorViewResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The page was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_page_ocr: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                page_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OCRPageResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The OCR page or segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_projects: {
        parameters: {
            query?: {
                status?: components["schemas"]["ProjectStatus"] | null;
                search?: string | null;
                sort?: "updated_at" | "name" | "status" | "progress";
                order?: "asc" | "desc";
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_project: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_project: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_project: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    archive_project: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    import_document: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_import_document"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentImportResponse"];
                };
            };
            /** @description The upload stream was interrupted. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The idempotent import conflicts. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The uploaded file is too large. */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request is not multipart. */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The upload metadata or content is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The analysis job could not be queued. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    analyze_glossary_impact: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GlossaryImpactRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GlossaryImpactResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The glossary operation conflicts with current state. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid glossary values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored glossary data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_reconstruction_readiness: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionReadinessResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    cancel_reconstruction: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionStatusResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    preview_reconstruction: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReconstructionPreviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionPreviewResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_reconstruction: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartReconstructionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionJobResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_reconstruction_status: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionStatusResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_review_queue: {
        parameters: {
            query?: {
                severity?: string | null;
                warning_type?: string | null;
                warning?: boolean | null;
                confidence_max?: number | null;
                page_id?: string | null;
                section_id?: string | null;
                status?: string | null;
                review_status?: components["schemas"]["ReviewStatus"] | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewQueueResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_translation_readiness: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranslationReadinessResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or translation job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Translation readiness or job state prevents the operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    cancel_translation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CancelTranslationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranslationStatusResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or translation job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Translation readiness or job state prevents the operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    retry_failed_translation: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryTranslationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranslationStatusResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or translation job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Translation readiness or job state prevents the operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    start_translation: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartTranslationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranslationJobResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or translation job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Translation readiness or job state prevents the operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The translation queue is not configured. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_translation_status: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TranslationStatusResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or translation job was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Translation readiness or job state prevents the operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    unarchive_project: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_warnings: {
        parameters: {
            query?: {
                status?: components["schemas"]["WarningStatus"] | null;
                severity?: components["schemas"]["WarningSeverity"] | null;
                warning_type?: components["schemas"]["WarningType"] | null;
                page_id?: string | null;
                segment_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarningListResponse"];
                };
            };
            /** @description The warning resolution is blocked by the quality policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or warning was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The warning has already been resolved. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_reconstruction_page: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                reconstruction_page_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionPageResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    retry_reconstruction_page: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                reconstruction_page_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetryReconstructionPageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconstructionJobResponse"];
                };
            };
            /** @description The reconstruction resource was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction state does not allow this operation. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The reconstruction queue is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_segment_revision: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentRevisionDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment or revision was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    bulk_segment_action: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BulkSegmentActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BulkSegmentActionResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The translation queue is not configured. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    approve_segment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveSegmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    restore_segment_revision: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RestoreRevisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RestoreRevisionResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment or revision was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_segment_revisions: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentRevisionListResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment or revision was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    resolve_segment_source: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceResolutionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceResolutionResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The OCR page or segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    edit_segment_translation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EditSegmentTranslationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    unapprove_segment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                segment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UnapproveSegmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SegmentDataResponse"];
                };
            };
            /** @description The request was rejected by the local security policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment revision is stale. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The segment is locked. */
            423: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_settings: {
        parameters: {
            query?: {
                category?: components["schemas"]["SettingCategory"] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsListResponse"];
                };
            };
            /** @description The setting key is not allowed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting value is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored setting data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    validate_settings: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ValidateSettingsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingsValidationResponse"];
                };
            };
            /** @description The setting key is not allowed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting value is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored setting data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_setting: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingDataResponse"];
                };
            };
            /** @description The setting key is not allowed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting value is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored setting data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_setting: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateSettingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SettingDataResponse"];
                };
            };
            /** @description The setting key is not allowed. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The setting value is invalid. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Stored setting data is invalid. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_system_health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemHealthResponse"];
                };
            };
            /** @description The request origin is not allowed. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_warning: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                warning_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarningDataResponse"];
                };
            };
            /** @description The warning resolution is blocked by the quality policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or warning was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The warning has already been resolved. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    accept_warning: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                warning_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WarningNoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarningDataResponse"];
                };
            };
            /** @description The warning resolution is blocked by the quality policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or warning was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The warning has already been resolved. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    mark_warning_false_positive: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                warning_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WarningNoteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarningDataResponse"];
                };
            };
            /** @description The warning resolution is blocked by the quality policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or warning was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The warning has already been resolved. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    resolve_warning: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                warning_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResolveWarningRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WarningDataResponse"];
                };
            };
            /** @description The warning resolution is blocked by the quality policy. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The project or warning was not found. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The warning has already been resolved. */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description The request contains invalid values. */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description The request origin is not allowed. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description An unexpected server error was normalized. */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
