// This file is generated. Do not edit manually.

export interface paths {
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
        /** ComponentHealth */
        ComponentHealth: {
            /**
             * Status
             * @default UNAVAILABLE
             * @constant
             */
            status: "UNAVAILABLE";
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
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
        };
    };
}
