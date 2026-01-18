"use client";

import { LessonPruningPanel } from "@/components/brain/lesson-pruning";
import { CacheManagement } from "@/components/brain/cache-management";

export function HygienePanel() {
    return (
        <div className="space-y-6 animate-in fade-in">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Left Column: Cache & Global Memory */}
                <div className="space-y-6">
                    <CacheManagement />
                </div>

                {/* Right Column: Lessons Statistics or Future Widgets */}
                <div className="space-y-6">
                    {/* Placeholder for future expansion or just moving stats here if we want */}
                </div>
            </div>

            {/* Full Width: Lesson Pruning (as it has its own grid layout) */}
            <LessonPruningPanel />
        </div>
    );
}
