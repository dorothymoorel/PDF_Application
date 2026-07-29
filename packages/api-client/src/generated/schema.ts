// This file is generated. Do not edit manually.

export interface paths {
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
