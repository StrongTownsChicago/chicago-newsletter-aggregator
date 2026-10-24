
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  
  "public": {
          Tables: {
            "email_source_mappings": {
                  Row: {
                    "created_at": string | null,"email_pattern": string,"id": number,"notes": string | null,"source_id": number
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string | null,"email_pattern": string,"id"?: number,"notes"?: string | null,"source_id": number
                  }
                  Update: {
                    "created_at"?: string | null,"email_pattern"?: string,"id"?: number,"notes"?: string | null,"source_id"?: number
                  }
                  Relationships: [
                    {
      foreignKeyName: "email_source_mappings_source_id_fkey"
      columns: ["source_id"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"newsletters": {
                  Row: {
                    "created_at": string | null,"email_uid": string | null,"entities": Json | null,"from_email": string | null,"id": string,"plain_text": string | null,"raw_html": string | null,"received_date": string,"relevance_score": number | null,"search_vector": unknown,"source_id": number,"subject": string,"summary": string | null,"to_email": string | null,"topics": (string)[] | null
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string | null,"email_uid"?: string | null,"entities"?: Json | null,"from_email"?: string | null,"id"?: string,"plain_text"?: string | null,"raw_html"?: string | null,"received_date": string,"relevance_score"?: number | null,"search_vector"?: never,"source_id": number,"subject": string,"summary"?: string | null,"to_email"?: string | null,"topics"?: (string)[] | null
                  }
                  Update: {
                    "created_at"?: string | null,"email_uid"?: string | null,"entities"?: Json | null,"from_email"?: string | null,"id"?: string,"plain_text"?: string | null,"raw_html"?: string | null,"received_date"?: string,"relevance_score"?: number | null,"search_vector"?: never,"source_id"?: number,"subject"?: string,"summary"?: string | null,"to_email"?: string | null,"topics"?: (string)[] | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "newsletters_source_id_fkey"
      columns: ["source_id"]
isOneToOne: false
      referencedRelation: "sources"
      referencedColumns: ["id"]
    }
                  ]
                },"notification_history": {
                  Row: {
                    "delivery_type": string,"digest_batch_id": string | null,"error_message": string | null,"id": string,"newsletter_ids": (string)[],"resend_email_id": string | null,"rule_ids": (string)[],"sent_at": string,"success": boolean,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "delivery_type": string,"digest_batch_id"?: string | null,"error_message"?: string | null,"id"?: string,"newsletter_ids": (string)[],"resend_email_id"?: string | null,"rule_ids": (string)[],"sent_at"?: string,"success": boolean,"user_id": string
                  }
                  Update: {
                    "delivery_type"?: string,"digest_batch_id"?: string | null,"error_message"?: string | null,"id"?: string,"newsletter_ids"?: (string)[],"resend_email_id"?: string | null,"rule_ids"?: (string)[],"sent_at"?: string,"success"?: boolean,"user_id"?: string
                  }
                  Relationships: [
                    
                  ]
                },"notification_queue": {
                  Row: {
                    "created_at": string,"digest_batch_id": string | null,"error_message": string | null,"id": string,"newsletter_id": string | null,"notification_type": string | null,"report_id": string | null,"rule_id": string,"sent_at": string | null,"status": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"digest_batch_id"?: string | null,"error_message"?: string | null,"id"?: string,"newsletter_id"?: string | null,"notification_type"?: string | null,"report_id"?: string | null,"rule_id": string,"sent_at"?: string | null,"status"?: string,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"digest_batch_id"?: string | null,"error_message"?: string | null,"id"?: string,"newsletter_id"?: string | null,"notification_type"?: string | null,"report_id"?: string | null,"rule_id"?: string,"sent_at"?: string | null,"status"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "notification_queue_newsletter_id_fkey"
      columns: ["newsletter_id"]
isOneToOne: false
      referencedRelation: "newsletters"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notification_queue_report_id_fkey"
      columns: ["report_id"]
isOneToOne: false
      referencedRelation: "weekly_topic_reports"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notification_queue_rule_id_fkey"
      columns: ["rule_id"]
isOneToOne: false
      referencedRelation: "notification_rules"
      referencedColumns: ["id"]
    }
                  ]
                },"notification_rules": {
                  Row: {
                    "created_at": string,"delivery_frequency": string | null,"id": string,"is_active": boolean,"min_relevance_score": number | null,"name": string,"search_term": string | null,"source_ids": (number)[] | null,"topics": (string)[],"updated_at": string,"user_id": string,"ward_numbers": (string)[] | null
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"delivery_frequency"?: string | null,"id"?: string,"is_active"?: boolean,"min_relevance_score"?: number | null,"name": string,"search_term"?: string | null,"source_ids"?: (number)[] | null,"topics"?: (string)[],"updated_at"?: string,"user_id": string,"ward_numbers"?: (string)[] | null
                  }
                  Update: {
                    "created_at"?: string,"delivery_frequency"?: string | null,"id"?: string,"is_active"?: boolean,"min_relevance_score"?: number | null,"name"?: string,"search_term"?: string | null,"source_ids"?: (number)[] | null,"topics"?: (string)[],"updated_at"?: string,"user_id"?: string,"ward_numbers"?: (string)[] | null
                  }
                  Relationships: [
                    
                  ]
                },"sources": {
                  Row: {
                    "email_address": string | null,"id": number,"name": string,"newsletter_archive_url": string | null,"phone": string | null,"signup_url": string | null,"source_type": string,"ward_number": string | null,"website": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "email_address"?: string | null,"id"?: number,"name": string,"newsletter_archive_url"?: string | null,"phone"?: string | null,"signup_url"?: string | null,"source_type": string,"ward_number"?: string | null,"website"?: string | null
                  }
                  Update: {
                    "email_address"?: string | null,"id"?: number,"name"?: string,"newsletter_archive_url"?: string | null,"phone"?: string | null,"signup_url"?: string | null,"source_type"?: string,"ward_number"?: string | null,"website"?: string | null
                  }
                  Relationships: [
                    
                  ]
                },"user_profiles": {
                  Row: {
                    "created_at": string,"email": string,"id": string,"notification_preferences": NonNullable<Json>,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"email": string,"id": string,"notification_preferences"?: NonNullable<Json>,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"email"?: string,"id"?: string,"notification_preferences"?: NonNullable<Json>,"updated_at"?: string
                  }
                  Relationships: [
                    
                  ]
                },"weekly_topic_reports": {
                  Row: {
                    "created_at": string,"id": string,"key_developments": Json | null,"newsletter_ids": (string)[],"report_summary": string,"topic": string,"week_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"key_developments"?: Json | null,"newsletter_ids": (string)[],"report_summary": string,"topic": string,"week_id": string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"key_developments"?: Json | null,"newsletter_ids"?: (string)[],"report_summary"?: string,"topic"?: string,"week_id"?: string
                  }
                  Relationships: [
                    
                  ]
                }
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "count_user_rules":
{ Args: { "user_uuid": string }; Returns: number
                           },
"get_active_weekly_topics":
{ Args: Record<PropertyKey, never>; Returns: {
              "topic": string
            }[]
                           },
"get_week_date_range":
{ Args: { "week_id_param": string }; Returns: {
              "week_end": string,"week_start": string
            }[]
                           },
"search_term_timeline":
{ Args: { "search_query": string }; Returns: {
              "month": string,"newsletter_count": number,"ward_count": number
            }[]
                           }
          }
          Enums: {
            [_ in never]: never
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "public": {
          Enums: {
            
          }
        }
} as const
