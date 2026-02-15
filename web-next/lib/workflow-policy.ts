import { Node } from "@xyflow/react";

// Define Node Categories (Swimlanes)
export const NODE_CATEGORIES = {
    DECISION: "decision",
    INTENT: "intent",
    KERNEL: "kernel",
    RUNTIME: "runtime",
    PROVIDER: "provider",
    EMBEDDING: "embedding",
} as const;

export type NodeCategory = (typeof NODE_CATEGORIES)[keyof typeof NODE_CATEGORIES];

// Define Allowed Connections (Source Category -> Target Category[])
const ALLOWED_CONNECTIONS: Record<NodeCategory, NodeCategory[]> = {
    [NODE_CATEGORIES.DECISION]: [NODE_CATEGORIES.INTENT],
    [NODE_CATEGORIES.INTENT]: [NODE_CATEGORIES.KERNEL],
    [NODE_CATEGORIES.KERNEL]: [NODE_CATEGORIES.RUNTIME, NODE_CATEGORIES.EMBEDDING],
    [NODE_CATEGORIES.RUNTIME]: [NODE_CATEGORIES.PROVIDER],
    [NODE_CATEGORIES.PROVIDER]: [], // End of chain usually
    [NODE_CATEGORIES.EMBEDDING]: [NODE_CATEGORIES.PROVIDER], // Logic: Embedding needs a provider
};

export interface ValidationResult {
    isValid: boolean;
    reason?: string;
}

export function getNodeCategory(nodeType: string): NodeCategory | undefined {
    // Simple mapping, assuming node.type matches category for now.
    // In real app, might need more complex logic or categorization.
    return Object.values(NODE_CATEGORIES).find((c) => c === nodeType);
}

export function validateConnection(source: Node, target: Node): ValidationResult {
    const sourceCategory = getNodeCategory(source.type || "");
    const targetCategory = getNodeCategory(target.type || "");

    if (!sourceCategory || !targetCategory) {
        return { isValid: false, reason: "unknown_node_type" };
    }

    const allowedTargets = ALLOWED_CONNECTIONS[sourceCategory];
    if (allowedTargets?.includes(targetCategory)) {
        return { isValid: true };
    }

    return {
        isValid: false,
        reason: `invalid_connection: ${sourceCategory} cannot connect to ${targetCategory}`
    };
}

export function getSwimlaneForCategory(category: NodeCategory): number {
    // Return X position order for swimlanes? Or Y?
    // Let's assume vertical swimlanes (Left -> Right flow) for now, or Horizontal (Top -> Bottom).
    // The previous layout was Top-to-Bottom (rankdir: "TB").

    // Ordered categories
    const order = [
        NODE_CATEGORIES.DECISION,
        NODE_CATEGORIES.INTENT,
        NODE_CATEGORIES.KERNEL,
        NODE_CATEGORIES.RUNTIME,
        NODE_CATEGORIES.EMBEDDING, // Parallel to Runtime or after?
        NODE_CATEGORIES.PROVIDER,
    ];

    // Embedding is a bit special, often parallel to runtime or kernel.
    // Let's stick to a simple index for now.
    return order.indexOf(category);
}
