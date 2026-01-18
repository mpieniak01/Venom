"use client";

import { Github, Globe, Linkedin, CodeXml } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

export function AuthorSignature() {
    const t = useTranslation();

    const links = [
        {
            label: "GitHub",
            href: "https://github.com/mpieniak01",
            icon: Github,
            color: "text-zinc-400 hover:text-white",
        },
        {
            label: "LinkedIn",
            href: "https://www.linkedin.com/in/mpieniak/",
            icon: Linkedin,
            color: "text-blue-400 hover:text-blue-300",
        },
        {
            label: "Website",
            href: "https://pieniak.it/",
            icon: Globe,
            color: "text-emerald-400 hover:text-emerald-300",
        },
    ];

    return (
        <div className="mt-6 border-t border-white/5 pt-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                    <CodeXml className="h-3 w-3" />
                    <span>{t("sidebar.author.createdBy")} <span className="text-zinc-400 font-medium">mpieniak</span></span>
                </div>
                <div className="flex items-center gap-1">
                    {links.map((link) => (
                        <Button
                            key={link.label}
                            asChild
                            variant="ghost"
                            size="sm"
                            className={cn("h-8 w-8 p-0 rounded-full flex items-center justify-center", link.color)}
                        >
                            <a href={link.href} target="_blank" rel="noopener noreferrer" title={link.label}>
                                <link.icon className="h-4 w-4" />
                            </a>
                        </Button>
                    ))}
                </div>
            </div>
        </div>
    );
}
