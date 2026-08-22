// This file is generated. Do not edit manually.

export interface paths {
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
        /**
         * BackupType
         * @description Supported backup scopes.
         * @enum {string}
         */
        BackupType: "DATABASE_ONLY" | "METADATA" | "FULL_PROJECTS" | "FULL_APPLICATION" | "PRE_RESTORE";
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
        /** CursorPagination */
        CursorPagination: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Next Cursor */
            next_cursor: string | null;
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
         * ReconstructionMode
         * @enum {string}
         */
        ReconstructionMode: "OVERLAY" | "REFLOW" | "HYBRID";
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
        /** RetryJobRequest */
        RetryJobRequest: {
            /** Retry Failed Items Only */
            retry_failed_items_only: boolean;
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
        /**
         * ReviewStatus
         * @enum {string}
         */
        ReviewStatus: "NOT_REVIEWED" | "REVIEW_REQUIRED" | "IN_REVIEW" | "EDITED" | "APPROVED" | "REJECTED";
        /** SegmentConfidenceResponse */
        SegmentConfidenceResponse: {
            /** Overall */
            overall?: number | null;
        };
        /**
         * SegmentStatus
         * @enum {string}
         */
        SegmentStatus: "CREATED" | "EXTRACTED" | "OCR_REQUIRED" | "OCR_COMPLETED" | "NORMALIZED" | "TERMS_DETECTED" | "PROTECTED" | "READY_FOR_TRANSLATION" | "TRANSLATING" | "MACHINE_TRANSLATED" | "TRANSLATION_FAILED" | "NEEDS_REVIEW" | "USER_EDITED" | "APPROVED" | "LOCKED" | "IGNORED" | "NOT_TRANSLATABLE";
        /**
         * SemanticRole
         * @enum {string}
         */
        SemanticRole: "TITLE" | "CHAPTER_TITLE" | "SECTION_TITLE" | "BODY_TEXT" | "DEFINITION" | "EXAMPLE" | "WARNING" | "NOTE" | "TIP" | "QUOTE" | "CAPTION" | "REFERENCE" | "CODE" | "FORMULA" | "NAVIGATION" | "DECORATION";
        /** StagedUploadData */
        StagedUploadData: {
            /** Original Filename */
            original_filename: string;
            /** Project Id */
            project_id: string;
            /** Set As Active */
            set_as_active: boolean;
            /** Size Bytes */
            size_bytes: number;
            /**
             * Status
             * @default STAGED
             * @constant
             */
            status: "STAGED";
            /** Upload Id */
            upload_id: string;
        };
        /** StagedUploadResponse */
        StagedUploadResponse: {
            data: components["schemas"]["StagedUploadData"];
            meta: components["schemas"]["ResponseMeta"];
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
        /** UpdateProjectRequest */
        UpdateProjectRequest: {
            /** Name */
            name?: string | null;
            reconstruction_mode?: components["schemas"]["ReconstructionMode"] | null;
            translation_style?: components["schemas"]["TranslationStyle"] | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
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
                    "application/json": components["schemas"]["StagedUploadResponse"];
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
