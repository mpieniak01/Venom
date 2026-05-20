# =============================================================================
# Legacy aliases kept for compatibility during deprecation
# =============================================================================

.PHONY: start2 startpre stoppre restartpre statuspre apipre webpre testpre ensurepreenv prebackup prerestore preverify preaudit predrill prereadiness

define legacy_alias
$(1):
	@echo "⚠️  DEPRECATED: use $(2) instead of $(1)"
	@$(MAKE) --no-print-directory $(2)
endef

$(eval $(call legacy_alias,start2,start-dev-turbo))

$(eval $(call legacy_alias,startpre,start-preprod))
$(eval $(call legacy_alias,stoppre,stop))
$(eval $(call legacy_alias,statuspre,status))
$(eval $(call legacy_alias,apipre,api-preprod))
$(eval $(call legacy_alias,webpre,web-preprod))
$(eval $(call legacy_alias,testpre,test-preprod-readonly-smoke))
$(eval $(call legacy_alias,ensurepreenv,ensure-preprod-env-file))

$(eval $(call legacy_alias,prebackup,preprod-backup))
$(eval $(call legacy_alias,prerestore,preprod-restore))
$(eval $(call legacy_alias,preverify,preprod-verify))
$(eval $(call legacy_alias,preaudit,preprod-audit))
$(eval $(call legacy_alias,predrill,preprod-drill))
$(eval $(call legacy_alias,prereadiness,preprod-readiness-check))

restartpre:
	@echo "⚠️  DEPRECATED: use stop + start-preprod instead of restartpre"
	@$(MAKE) --no-print-directory stop
	@$(MAKE) --no-print-directory start-preprod
