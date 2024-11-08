package com.elixir.biohackaton.ISAToSRA.receipt.isamodel;

import java.util.ArrayList;
import lombok.Data;
import lombok.experimental.FieldNameConstants;

@Data
@FieldNameConstants
public class Study {
  public String identifier;
  public String title;
  public String description;
  public String submissionDate;
  public String publicReleaseDate;
  public String filename;
  public ArrayList<Comment> comments;
  public ArrayList<Object> publications;
  public ArrayList<Person> people;
  public ArrayList<Object> studyDesignDescriptors;
  public ArrayList<CharacteristicCategory> characteristicCategories;
  public Materials materials;
  public ArrayList<Protocol> protocols;
  public ArrayList<ProcessSequence> processSequence;
  public ArrayList<Assay> assays;
  public ArrayList<Object> factors;
  public ArrayList<Object> unitCategories;
}
