package com.elixir.biohackaton.ISAToSRA.sra.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonInclude.Include;

import lombok.Builder;
import lombok.Data;

@Builder
@Data
public class MarsReceiptInfo {
    @JsonInclude(Include.NON_NULL)
    private String name;

    private String message;
}
