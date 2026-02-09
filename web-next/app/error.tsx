"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function AppErrorPage({
    error,
    reset,
}: Readonly<{
    error: Error & { digest?: string };
    reset: () => void;
}>) {
    useEffect(() => {
        console.error(error);
    }, [error]);

    return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-950 p-6 text-center text-zinc-100" data-testid="app-error">
            <h2 className="text-xl font-bold text-red-400">Something went wrong!</h2>
            <p className="max-w-md text-sm text-zinc-400">{error.message}</p>
            {error.digest && <p className="text-xs text-zinc-600 font-mono">Digest: {error.digest}</p>}
            <Button
                onClick={() => reset()}
                variant="outline"
            >
                Try again
            </Button>
        </div>
    );
}
